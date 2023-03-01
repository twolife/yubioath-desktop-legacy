#!/usr/bin/env python
# -*- coding: utf-8 -*-

import dataclasses
import os
import sys
import ctypes
import struct
import json
import logging
import types
import ykman.logging_setup
import smartcard.pcsc.PCSCExceptions
from base64 import b32encode, b32decode, b64decode
from binascii import a2b_hex, b2a_hex
from threading import Event, Thread
from typing import Optional

from time import sleep

from fido2.ctap import CtapError
from fido2.ctap2 import Ctap2, ClientPin, FPBioEnrollment, CredentialManagement, CaptureError
from ykman.pcsc import list_readers, list_devices as list_ccid
from ykman.settings import AppData
from ykman.oath import is_hidden, is_steam, calculate_steam
from ykman.scancodes import KEYBOARD_LAYOUT, encode

from yubikit.management import (
    TRANSPORT, CAPABILITY, Mode, USB_INTERFACE, ManagementSession, DeviceConfig)
from yubikit.core import CommandError, TimeoutError
from yubikit.core.otp import modhex_decode, modhex_encode, OtpConnection
from yubikit.core.smartcard import ApduError, SW, SmartCardConnection
from yubikit.core.fido import FidoConnection
from yubikit.oath import (
    OathSession, Credential, OATH_TYPE, CredentialData, parse_b32_key, HASH_ALGORITHM, Code)
from yubikit.yubiotp import (
    YubiOtpSession, YubiOtpSlotConfiguration,
    StaticPasswordSlotConfiguration, HotpSlotConfiguration, HmacSha1SlotConfiguration)
from smartcard.Exceptions import NoCardException, CardConnectionException

from ykman.scancodes import KEYBOARD_LAYOUT

import pyotherside

from ykman import __version__ as ykman_v

if int(ykman_v.split(".")[0] ) > 4:
    from yubikit.support import get_name, read_info
    from ykman.device import list_all_devices, scan_devices
    from ykman.otp import (
    _PrepareUploadFailed as PrepareUploadFailed
    , _prepare_upload_key as prepare_upload_key, generate_static_pw, time_challenge, format_oath_code)
else:
    from ykman.device import scan_devices, list_all_devices, get_name, read_info
    from ykman.otp import PrepareUploadFailed, generate_static_pw, prepare_upload_key, time_challenge, format_oath_code


logger = logging.getLogger(__name__)



def as_json(f):
    def wrapped(*args):
        return json.dumps(f(*(json.loads(a) for a in args)))
    return wrapped


def cred_to_dict(cred):
    return {
        'device_id': cred.device_id,
        'key': cred.id.decode('utf8'),
        'issuer': cred.issuer,
        'name': cred.name,
        'oath_type': cred.oath_type.name,
        'period': cred.period,
        'touch': cred.touch_required
    }


def cred_from_dict(data):
    return Credential(
        data['device_id'],
        data['key'].encode('utf-8'),
        data.get('issuer'),
        data['name'],
        OATH_TYPE[data['oath_type']],
        data['period'],
        data['touch']
    )


def code_to_dict(code):
    return {
        'value': code.value,
        'valid_from': code.valid_from,
        'valid_to': min(code.valid_to, 9999999999)  # No Inf in JSON.
    } if code else None


def pair_to_dict(cred, code):
    return {
        'credential': cred_to_dict(cred),
        'code': code_to_dict(code)
    }


def credential_data_to_dict(credentialData):
    return {
        'secret': b32encode(credentialData.secret).decode(),
        'issuer': credentialData.issuer,
        'name': credentialData.name,
        'oath_type': credentialData.oath_type.name,
        'algorithm': credentialData.hash_algorithm.name,
        'digits': credentialData.digits,
        'period': credentialData.period,
        'counter': credentialData.counter,
        'touch': False
    }


def success(result={}):
    result['success'] = True
    return result


def failure(err_id, result={}):
    result['success'] = False
    result['error_id'] = err_id
    return result


def unknown_failure(exception):
    return failure(str(exception))


def catch_error(f):
    def wrapped(*args, **kwargs):
        try:
            return f(*args, **kwargs)

        except ApduError as e:
            if e.sw == SW.SECURITY_CONDITION_NOT_SATISFIED:
                return failure('access_denied')
            logger.error('Uncaught exception', exc_info=e)
            return unknown_failure(e)
        except smartcard.pcsc.PCSCExceptions.EstablishContextException:
            return failure('no_pcscd')
        except Exception as e:
            if str(e) == 'Incorrect padding':
                return failure('incorrect_padding')
            logger.error('Uncaught exception', exc_info=e)
            return unknown_failure(e)
    return wrapped


def is_nfc(reader_name):
    return "yubico" not in reader_name.lower()


def interfaces_from_capabilities(capabilities):
    interfaces= []
    if CAPABILITY.OTP & capabilities:
        interfaces.append("OTP")
    if (CAPABILITY.U2F | CAPABILITY.FIDO2) & capabilities:
        interfaces.append("FIDO")
    if (CAPABILITY.OATH | CAPABILITY.PIV | CAPABILITY.OPENPGP) & capabilities:
        interfaces.append("CCID")
    return interfaces


class Controller(object):

    _devs = {}
    _devices = []

    _current_serial = None
    _current_derived_key = None

    _reader_filter = None
    _readers = []

    _state = None

    _event = None
    _pin = None

    _win_non_admin = sys.platform == "win32" and not ctypes.windll.shell32.IsUserAnAdmin()

    def __init__(self):
        self.settings = AppData('oath')

        # Wrap all args and return values as JSON.
        for f in dir(self):
            if not f.startswith('_'):
                func = getattr(self, f)
                if isinstance(func, types.MethodType):
                    setattr(self, f, as_json(catch_error(func)))

    def _open_device(self, connection_types=[SmartCardConnection, FidoConnection, OtpConnection]):
        if self._reader_filter:
            dev = self._get_dev_from_reader()
            if dev:
                return dev.open_connection(connection_types[0])
            else:
                raise ValueError('no_device_custom_reader')

        if int(ykman_v.split(".")[0] ) > 4:
            devs = list_all_devices(connection_types)
            if len(devs) == 0:
                raise Exception("No YubiKey connected")
            elif len(devs) != 1:
                raise Exception("More than one YubiKey connected")
            dev, info2 = devs[0]

            for conn_type in connection_types:
                try:
                    return dev.open_connection(conn_type)
                except Exception:
                    logger.debug(f"Failed connecting to the YubiKey over {conn_type}", exc_info=True)
        else:
            return connect_to_device(self._current_serial, connection_types=connection_types)[0]

    def _open_oath(self):
        if self._reader_filter:
            dev = self._get_dev_from_reader()
            if dev:
                return dev.open_connection(SmartCardConnection)
            else:
                raise ValueError('no_device_custom_reader')

        if int(ykman_v.split(".")[0] ) > 4:
            devs = list_all_devices([SmartCardConnection])
            if len(devs) == 0:
                raise Exception("No YubiKey connected")
            elif len(devs) != 1:
                raise Exception("More than one YubiKey connected")
            dev, info2 = devs[0]
            return dev.open_connection(SmartCardConnection)
        else:
            return connect_to_device(self._current_serial, [SmartCardConnection])[0]

    def is_win_non_admin(self):
        return success({'winNonAdmin': self._win_non_admin})

    def check_descriptors(self):
        old_state = self._state
        self._devs, self._state = scan_devices()
        return success({
            'usbDescriptorsChanged': self._state != old_state
        })

    def _readers_changed(self, filter):
        old_readers = self._readers
        self._readers = []
        for dev in list_ccid(filter):
            try:
                with dev.open_connection(SmartCardConnection) as c:
                    self._readers.append(dev)
            except:
                pass
        readers_changed = len(self._readers) != len(old_readers)
        return readers_changed

    def check_readers(self, filter):
        return success({
            'needToRefresh': self._readers_changed(filter)
        })

    def _get_dev_from_reader(self):
        readers = list_ccid(self._reader_filter)
        if len(readers) == 1:
            dev = readers[0]
            return dev
        return None

    def _get_devices(self, otp_mode=False):
        res = []
        for dev, info in list_all_devices():
            res.append(self._serialise_dev(dev, info))
        return res

    def _get_fido_status(self):
        fido_has_pin = False
        fido_retries = 0
        uv_blocked = False
        try:
            with self._open_device([FidoConnection]) as conn:
                ctap2 = Ctap2(conn)
                options = ctap2.info.options
                available = True

                fido_has_pin = options.get("clientPin")
                if fido_has_pin:
                    client_pin = ClientPin(ctap2)
                    fido_retries = client_pin.get_pin_retries()[0]

                    if ctap2.info.options.get("bioEnroll"):
                        uv_retries = client_pin.get_uv_retries()[0]
                        if uv_retries == 0:
                            uv_blocked = True
        except Exception as e:
            logger.debug("Failed to read CTAP info", exc_info=e)
            available = False

        return available, [fido_has_pin, fido_retries, uv_blocked]

    def _serialise_dev(self, dev, info):

        def _get_version(dev):
            if dev.version:
                return '.'.join(str(x) for x in dev.version)
            if hasattr(dev, '_desc_version') and dev._desc_version:
                return '.'.join(str(x) for x in dev._desc_version)
            return ''

        ctap_available, fido_pin_list = self._get_fido_status()

        supported_interfaces = interfaces_from_capabilities(
                info.supported_capabilities.get(TRANSPORT.USB))

        if int(ykman_v.split(".")[0] ) > 4:
          return {
            'name': get_name(info, dev.pid.yubikey_type),
            'version': _get_version(info),
            'serial': info.serial or '',
            'usbAppEnabled': [
                a.name for a in CAPABILITY
                if a in info.config.enabled_capabilities.get(TRANSPORT.USB)],
            'usbAppSupported': [
                a.name for a in CAPABILITY
                if a in info.supported_capabilities.get(TRANSPORT.USB)],
            'nfcAppEnabled': [
                a.name for a in CAPABILITY
                if a in info.config.enabled_capabilities.get(TRANSPORT.NFC, [])],
            'nfcAppSupported': [
                a.name for a in CAPABILITY
                if a in info.supported_capabilities.get(TRANSPORT.NFC, [])],
            'usbInterfacesSupported': supported_interfaces,
            'usbInterfacesEnabled': [
                i.name for i in USB_INTERFACE
                if i in dev.pid.usb_interfaces],
            'canWriteConfig': info.version and info.version >= (5,0,0),
            'configurationLocked': info.is_locked,
            'formFactor': info.form_factor,
            'hasPassword': dev.has_password if hasattr(dev, 'has_password') else False,
            'ctapAvailable': ctap_available,
            'fidoHasPin': fido_pin_list[0],
            'fidoPinRetries': fido_pin_list[1],
            'uvBlocked': fido_pin_list[2],
            'isNfc': self._reader_filter and not self._reader_filter.lower().startswith("yubico yubikey"),
          }
        else:
          return {
            'name': get_name(info, dev.pid.get_type()),
            'version': _get_version(info),
            'serial': info.serial or '',
            'usbAppEnabled': [
                a.name for a in CAPABILITY
                if a in info.config.enabled_capabilities.get(TRANSPORT.USB)],
            'usbAppSupported': [
                a.name for a in CAPABILITY
                if a in info.supported_capabilities.get(TRANSPORT.USB)],
            'nfcAppEnabled': [
                a.name for a in CAPABILITY
                if a in info.config.enabled_capabilities.get(TRANSPORT.NFC, [])],
            'nfcAppSupported': [
                a.name for a in CAPABILITY
                if a in info.supported_capabilities.get(TRANSPORT.NFC, [])],
            'usbInterfacesSupported': supported_interfaces,
            'usbInterfacesEnabled': [
                i.name for i in USB_INTERFACE
                if i in dev.pid.get_interfaces()],
            'canWriteConfig': info.version and info.version >= (5,0,0),
            'configurationLocked': info.is_locked,
            'formFactor': info.form_factor,
            'hasPassword': dev.has_password if hasattr(dev, 'has_password') else False,
            'ctapAvailable': ctap_available,
            'fidoHasPin': fido_pin_list[0],
            'fidoPinRetries': fido_pin_list[1],
            'uvBlocked': fido_pin_list[2],
            'isNfc': self._reader_filter and not self._reader_filter.lower().startswith("yubico yubikey"),
          }

    def connect_custom_reader(self, reader_filter=None, otp_mode=False):
        def connect_custom_action(dev, event):

            removed = False
            while True:
                sleep(0.5)
                try:
                    with dev.open_connection(FidoConnection):
                        if (event.is_set()):
                            return
                        if removed:
                            sleep(1.0)  # Wait for the device to settle
                            pyotherside.send("fido_reset", False, True)
                            return
                except CardConnectionException:
                    pass  # Expected, ignore
                except NoCardException:
                    removed = True
                    pyotherside.send("fido_reset", True, False)

        self._devices = []

        if not otp_mode and reader_filter:
            self._reader_filter = reader_filter
            dev = self._get_dev_from_reader()
            if dev:
                self._event = Event()
                Thread(target=connect_custom_action, args=(dev, self._event)).start()
        return success()

    def load_devices_custom_reader(self, reader_filter=None, otp_mode=False):
        self._devices = []

        if not otp_mode and reader_filter:
            self._reader_filter = reader_filter
            dev = self._get_dev_from_reader()
            if dev:
                with dev.open_connection(SmartCardConnection) as conn:
                    if int(ykman_v.split(".")[0] ) > 4:
                        info = read_info(conn, dev.pid)
                    else:
                        info = read_info(dev.pid, conn)

                    try:
                        oath = OathSession(conn)
                        has_password = oath.locked
                        selectable = True
                        self._current_serial = info.serial
                    except Exception:
                        selectable = False
                        has_password = False

                interfaces_enabled = interfaces_from_capabilities(
                        info.config.enabled_capabilities[TRANSPORT.USB])
                interfaces_supported = interfaces_from_capabilities(
                        info.supported_capabilities[TRANSPORT.USB])

                ctap_available, fido_pin_list = self._get_fido_status()

                self._devices.append({
                    'name': get_name(info, dev.pid.get_type() if dev.pid else None),
                    'version': '.'.join(str(d) for d in info.version),
                    'serial': info.serial or '',
                    'usbInterfacesEnabled': interfaces_enabled,
                    'usbInterfacesSupported': interfaces_supported,
                    'usbAppEnabled': [
                        a.name for a in CAPABILITY
                        if a in info.config.enabled_capabilities.get(TRANSPORT.USB)],
                    'usbAppSupported': [
                        a.name for a in CAPABILITY
                        if a in info.supported_capabilities.get(TRANSPORT.USB)],
                    'nfcAppEnabled': [
                        a.name for a in CAPABILITY
                        if a in info.config.enabled_capabilities.get(TRANSPORT.NFC, [])],
                    'nfcAppSupported': [
                        a.name for a in CAPABILITY
                        if a in info.supported_capabilities.get(TRANSPORT.NFC, [])],
                    'hasPassword': has_password,
                    'ctapAvailable': ctap_available,
                    'formFactor': info.form_factor,
                    'fidoHasPin': fido_pin_list[0],
                    'fidoPinRetries': fido_pin_list[1],
                    'isNfc': self._reader_filter and not self._reader_filter.lower().startswith("yubico yubikey"),
                    'selectable': selectable,
                    'validated': True  # not has_password
                })

                return success({'devices': self._devices})
            else:
                return success({'devices': []})

    def load_devices_usb(self, otp_mode=False):
        self._reader_filter = None
        # Forget current serial and derived key if no descriptors
        # Return empty list of devices
        if not self._devs:
            self._current_serial = None
            self._current_derived_key = None
            return success({'devices': []})

        self._devices = self._get_devices(otp_mode)
        win_fido = False
        no_access = sum(self._devs.values()) > len(self._devices)
        if no_access:
          if int(ykman_v.split(".")[0] ) > 4:
              if self._win_non_admin and \
                    any(pid.usb_interfaces == USB_INTERFACE.FIDO for pid in self._devs.keys()):
                win_fido = True
          else:
              if self._win_non_admin and \
                    any(pid.get_interfaces() == USB_INTERFACE.FIDO for pid in self._devs.keys()):
                win_fido = True

        # If no current serial, or current serial seems removed,
        # select the first serial found.
        if not self._current_serial or (
                self._current_serial not in [
                    dev['serial'] for dev in self._devices]):
            for dev in self._devices:
                if dev['serial']:
                    self._current_serial = dev['serial']
                    break
        return success({'devices': self._devices, 'noAccess': no_access, 'winFido': win_fido})

    def _otp_get_code_or_touch(
                    self, slot, digits, timestamp, wait_for_touch=False):
        code = None
        with self._open_device([OtpConnection]) as oath_controller:
            session = YubiOtpSession(oath_controller)
            # Check that slot is not empty
            if not session.get_config_state().is_configured(slot):
                raise CommandError("not programmed")

            challenge = time_challenge(timestamp)

            try:
                event = Event()

                def on_keepalive(status):
                    if not hasattr(on_keepalive, "prompted") and status == 2 and not wait_for_touch:
                        on_keepalive.prompted = True
                        event.set()
                response = session.calculate_hmac_sha1(slot, challenge, event, on_keepalive)
                code = format_oath_code(response, int(digits))
                return code, False
            except TimeoutError:
                return code, hasattr(on_keepalive, "prompted")

    def otp_calculate_all(
                self, slot1_digits, slot2_digits, timestamp):
        valid_from = timestamp - (timestamp % 30)
        valid_to = valid_from + 30
        entries = []

        def calc(slot, digits, label):
            try:
                code, touch = self._otp_get_code_or_touch(slot, digits, timestamp)
                entries.append({
                    'credential': cred_to_dict(
                        Credential('', label.encode(), None, label, OATH_TYPE.TOTP, 30, touch)),
                    'code': code_to_dict(
                        Code(code, valid_from, valid_to)) if code else None
                })
            except CommandError as e:
                pass

        if slot1_digits:
            calc(1, slot1_digits, "Slot 1")

        if slot2_digits:
            calc(2, slot2_digits, "Slot 2")

        return success({'entries': entries})

    def otp_calculate(self, slot, digits, credential, timestamp):
        valid_from = timestamp - (timestamp % 30)
        valid_to = valid_from + 30
        code, _ = self._otp_get_code_or_touch(
            slot, digits, timestamp, wait_for_touch=True)
        return success({
            'credential': credential,
            'code': code_to_dict(Code(code, valid_from, valid_to))
        })

    def otp_slot_status(self):
        with self._open_device([OtpConnection]) as oath_controller:
            session = YubiOtpSession(oath_controller)
            state = session.get_config_state()
        return success({'status': (state.is_configured(1), state.is_configured(2))})

    def otp_add_credential(self, slot, key, touch):
        key = parse_b32_key(key)
        with self._open_device([OtpConnection]) as oath_controller:
            session = YubiOtpSession(oath_controller)
            session.put_configuration(
                int(slot),
                HmacSha1SlotConfiguration(key).require_touch(touch),
            )

        return success()

    def otp_delete_credential(self, slot):
        with self._open_device([OtpConnection]) as oath_controller:
            session = YubiOtpSession(oath_controller)
            session.delete_slot(slot)
        return success()

    def write_config(self, usb_applications, nfc_applications):

        usb_enabled = 0x00
        nfc_enabled = 0x00
        for app in usb_applications:
            usb_enabled |= CAPABILITY [app]
        for app in nfc_applications:
            nfc_enabled |= CAPABILITY [app]


        if self._reader_filter:
            with self._open_oath() as conn:
                session = ManagementSession(conn)
                session.write_device_config(
                    DeviceConfig(
                        {TRANSPORT.USB: usb_enabled,
                        TRANSPORT.NFC: nfc_enabled},
                        None,
                        None,
                        None,
                    ),
                    True)
        else:

            with self._open_device() as conn:
                session = ManagementSession(conn)
                session.write_device_config(
                    DeviceConfig(
                        {TRANSPORT.USB: usb_enabled,
                        TRANSPORT.NFC: nfc_enabled},
                        None,
                        None,
                        None,
                    ),
                    True)

                self._state = None
            sleep(1.0)
        return success()

    def slots_status(self):
        if self._reader_filter:
            with self._open_oath() as conn:
                session = YubiOtpSession(conn)
                state = session.get_config_state()
                slot1 = state.is_configured(1)
                slot2 = state.is_configured(2)
                ans = [slot1, slot2]
                return success({'status': ans})
        else:
            with self._open_device([OtpConnection]) as conn:
                session = YubiOtpSession(conn)
                state = session.get_config_state()
                slot1 = state.is_configured(1)
                slot2 = state.is_configured(2)
                ans = [slot1, slot2]
                return success({'status': ans})

    def erase_slot(self, slot):
        if self._reader_filter:
            with self._open_oath() as conn:
                session = YubiOtpSession(conn)
                session.delete_slot(slot)
        else:
            with self._open_device([OtpConnection]) as conn:
                session = YubiOtpSession(conn)
                session.delete_slot(slot)
        return success()

    def swap_slots(self):
        if self._reader_filter:
            with self._open_oath() as conn:
                session = YubiOtpSession(conn)
                session.swap_slots()
        else:
            with self._open_device([OtpConnection]) as conn:
                session = YubiOtpSession(conn)
                session.swap_slots()
        return success()

    def serial_modhex(self):
        if self._reader_filter:
            with self._open_oath() as conn:
                session = YubiOtpSession(conn)
                return modhex_encode(b'\xff\x00' + struct.pack(b'>I', session.get_serial()))

        else:
            with self._open_device([OtpConnection]) as conn:
                session = YubiOtpSession(conn)
                return modhex_encode(b'\xff\x00' + struct.pack(b'>I', session.get_serial()))

    def program_challenge_response(self, slot, key, touch):
        key = a2b_hex(key)
        if self._reader_filter:
            with self._open_oath() as conn:
                session = YubiOtpSession(conn)
                try:
                    session.put_configuration(
                        slot,
                        HmacSha1SlotConfiguration(key).require_touch(touch),
                    )
                except CommandError as e:
                    logger.debug("Failed to program Challenge-response", exc_info=e)
                    return failure("write error")
        else:
             with self._open_device([OtpConnection]) as conn:
                session = YubiOtpSession(conn)
                try:
                    session.put_configuration(
                        slot,
                        HmacSha1SlotConfiguration(key).require_touch(touch),
                    )
                except CommandError as e:
                    logger.debug("Failed to program Challenge-response", exc_info=e)
                    return failure("write error")

        return success()


    def program_static_password(self, slot, key, keyboard_layout):
        if self._reader_filter:
            with self._open_oath() as conn:
                session = YubiOtpSession(conn)
                scan_codes = encode(key, KEYBOARD_LAYOUT[keyboard_layout])

                try:
                    session.put_configuration(slot, StaticPasswordSlotConfiguration(scan_codes))
                except CommandError as e:
                    logger.debug("Failed to program static password", exc_info=e)
                    return failure("write error")
        else:
            with self._open_device([OtpConnection]) as conn:
                session = YubiOtpSession(conn)
                scan_codes = encode(key, KEYBOARD_LAYOUT[keyboard_layout])

                try:
                    session.put_configuration(slot, StaticPasswordSlotConfiguration(scan_codes))
                except CommandError as e:
                    logger.debug("Failed to program static password", exc_info=e)
                    return failure("write error")

        return success()

    def program_oath_hotp(self, slot, key, digits):
        unpadded = key.upper().rstrip('=').replace(' ', '')
        key = b32decode(unpadded + '=' * (-len(unpadded) % 8))

        if self._reader_filter:
            with self._open_oath() as conn:
                session = YubiOtpSession(conn)
                try:
                    session.put_configuration(
                        slot,
                        HotpSlotConfiguration(key)
                        .digits8(int(digits) == 8),
                    )
                except CommandError as e:
                    logger.debug("Failed to program OATH-HOTP", exc_info=e)
                    return failure("write error")
        else:
            with self._open_device([OtpConnection]) as conn:
                session = YubiOtpSession(conn)
                try:
                    session.put_configuration(
                        slot,
                        HotpSlotConfiguration(key)
                        .digits8(int(digits) == 8),
                    )
                except CommandError as e:
                    logger.debug("Failed to program OATH-HOTP", exc_info=e)
                    return failure("write error")
        return success()

    def generate_static_pw(self, keyboard_layout):
        return success({
            'password': generate_static_pw(
                38, KEYBOARD_LAYOUT[keyboard_layout])
        })

    def random_uid(self):
        return b2a_hex(os.urandom(6)).decode('ascii')

    def random_key(self, bytes):
        return b2a_hex(os.urandom(int(bytes))).decode('ascii')

    def program_otp(self, slot, public_id, private_id, key, upload=False,
                    app_version='unknown'):
        key = a2b_hex(key)
        public_id = modhex_decode(public_id)
        private_id = a2b_hex(private_id)

        upload_url = None

        if self._reader_filter:
            with self._open_oath() as conn:
                if upload:
                    try:
                        upload_url = prepare_upload_key(
                            key, public_id, private_id,
                            serial=self._current_serial,
                            user_agent='ykman-qt/' + app_version)
                    except PrepareUploadFailed as e:
                        logger.debug('YubiCloud upload failed', exc_info=e)
                        return failure('upload_failed',
                                       {'upload_errors': [err.name
                                                          for err in e.errors]})
                try:
                    session = YubiOtpSession(conn)
                    session.put_configuration(
                        slot,
                        YubiOtpSlotConfiguration(public_id, private_id, key)
                    )
                except CommandError as e:
                    logger.debug("Failed to program YubiOTP", exc_info=e)
                    return failure("write error")
        else:
            with self._open_device([OtpConnection]) as conn:
                if upload:
                    try:
                        upload_url = prepare_upload_key(
                            key, public_id, private_id,
                            serial=self._current_serial,
                            user_agent='ykman-qt/' + app_version)
                    except PrepareUploadFailed as e:
                        logger.debug('YubiCloud upload failed', exc_info=e)
                        return failure('upload_failed',
                                       {'upload_errors': [err.name
                                                          for err in e.errors]})
                try:
                    session = YubiOtpSession(conn)
                    session.put_configuration(
                        slot,
                        YubiOtpSlotConfiguration(public_id, private_id, key)
                    )
                except CommandError as e:
                    logger.debug("Failed to program YubiOTP", exc_info=e)
                    return failure("write error")

        logger.debug('YubiOTP successfully programmed.')
        if upload_url:
            logger.debug('Upload url: %s', upload_url)

        return success({'upload_url': upload_url})

    def set_mode(self, interfaces):
        interfaces_enabled = 0x00
        for usb_interface in interfaces:
            interfaces_enabled |= USB_INTERFACE [usb_interface]

        with self._open_device() as conn:
            try:
                session = ManagementSession(conn)
                session.set_mode(
                    Mode(interfaces_enabled))

            except ValueError as e:
                if str(e) == 'Configuration locked!':
                    return failure('interface_config_locked')
                raise

            return success()


    def select_current_serial(self, serial):
        self._current_serial = serial
        self._current_derived_key = None
        return success()

    def ccid_calculate_all(self, timestamp):
        with self._open_oath() as oath_controller:
            session = OathSession(oath_controller)
            self._unlock(session)
            entries = [
                pair_to_dict(
                    cred,
                    dataclasses.replace(code, value=calculate_steam(session, cred, timestamp))
                    if is_steam(cred) and not cred.touch_required
                    else code,
                )
                for (cred, code) in session.calculate_all(timestamp).items()
                if not is_hidden(cred)
            ]
            return success({"entries": entries})

    def ccid_calculate(self, credential, timestamp):
        with self._open_oath() as oath_controller:
            session = OathSession(oath_controller)
            self._unlock(session)
            cred = cred_from_dict(credential)
            if is_steam(cred):
                timestep = timestamp // cred.period
                valid_from = timestep * cred.period
                valid_to = valid_from + cred.period
                code = Code(calculate_steam(session, cred, timestamp), valid_from, valid_to)
            else:
                code = session.calculate_code(cred, timestamp)
            return success({"credential": credential, "code": code_to_dict(code)})

    def ccid_add_credential(
            self, name, secret, issuer, oath_type,
            algo, digits, period, touch, overwrite=False):
        secret = parse_b32_key(secret)
        with self._open_oath() as oath_controller:
            try:
                session = OathSession(oath_controller)
                cred_data = CredentialData(
                    name, OATH_TYPE[oath_type], HASH_ALGORITHM[algo],
                    secret,
                    int(digits), int(period), 0, issuer
                )
                self._unlock(session)
                if not overwrite:
                    key = cred_data.get_id()
                    if key in [cred.id for cred in session.list_credentials()]:
                        return failure('credential_already_exists')
                session.put_credential(cred_data, touch)
            except ApduError as e:
                # NEO doesn't return a no space error if full,
                # but a command aborted error. Assume it's because of
                # no space in this context.
                if e.sw in (SW.NO_SPACE, SW.COMMAND_ABORTED):
                    return failure('no_space')
                else:
                    raise
            return success()

    def ccid_validate(self, password, remember=False):
        with self._open_oath() as oath_controller:
            session = OathSession(oath_controller)
            key = session.derive_key(password)
            try:
                session.validate(key)
                self._current_derived_key = key
                if remember:
                    keys = self.settings.setdefault('keys', {})
                    keys[session.device_id] = b2a_hex(
                        self._current_derived_key).decode()
                    self.settings.write()
                return success()
            except ApduError as e:
                if e.sw == SW.INCORRECT_PARAMETERS:
                    return failure('validate_failed')

    def _unlock(self, controller):
        if controller.locked:
            keys = self.settings.get('keys', {})
            if self._current_derived_key is not None:
                controller.validate(self._current_derived_key)
            elif controller.device_id in keys:
                controller.validate(a2b_hex(keys[controller.device_id]))
            else:
                return failure('failed_to_unlock_key')

    def ccid_delete_credential(self, credential):
        with self._open_oath() as oath_controller:
            session = OathSession(oath_controller)
            self._unlock(session)
            session.delete_credential(cred_from_dict(credential).id)
            return success()

    def ccid_reset(self):
        with self._open_oath() as oath_controller:
            session = OathSession(oath_controller)
            session.reset()
            return success()

    def ccid_clear_local_passwords(self):
        self.settings.setdefault('keys', {})
        del self.settings['keys']
        self.settings.write()
        return success()

    def ccid_remove_password(self):
        with self._open_oath() as oath_controller:
            session = OathSession(oath_controller)
            self._unlock(session)
            session.unset_key()
            self._current_derived_key = None
            keys = self.settings.setdefault('keys', {})
            if session.device_id in keys:
                del keys[session.device_id]
            self.settings.write()
            return success()

    def ccid_set_password(self, new_password, remember=False):
        with self._open_oath() as oath_controller:
            session = OathSession(oath_controller)
            self._unlock(session)
            keys = self.settings.setdefault('keys', {})
            key = session.derive_key(new_password)
            session.set_key(key)
            self._current_derived_key = key
            if remember:
                keys[session.device_id] = b2a_hex(
                    self._current_derived_key).decode()
            elif session.device_id in keys:
                del keys[session.device_id]
            self.settings.write()
            return success()

    def get_connected_readers(self):
        return success({'readers': [reader.name for reader in list_readers()]})

    def parse_qr(self, data):
        try:
            return success(
                credential_data_to_dict(
                    CredentialData.parse_uri(data)))
        except Exception as e:
            logger.error('Failed to parse uri', exc_info=e)
            return failure('failed_to_parse_uri')
        return failure('no_credential_found')

    def fido_set_pin(self, new_pin):
        try:
            with self._open_device([FidoConnection]) as conn:
                ctap2 = Ctap2(conn)
                if len(new_pin) < ctap2.info.min_pin_length:
                    return failure('too short')
                client_pin = ClientPin(ctap2)
                client_pin.set_pin(new_pin)
                return success()
        except CtapError as e:
            if e.code == CtapError.ERR.INVALID_LENGTH or \
                    e.code == CtapError.ERR.PIN_POLICY_VIOLATION:
                return failure('too long')
            raise

    def fido_change_pin(self, current_pin, new_pin):
        try:
            with self._open_device([FidoConnection]) as conn:
                ctap2 = Ctap2(conn)
                if len(new_pin) < ctap2.info.min_pin_length:
                    return failure('too short')
                client_pin = ClientPin(ctap2)
                client_pin.change_pin(current_pin, new_pin)
                return success()
        except CtapError as e:
            if e.code == CtapError.ERR.INVALID_LENGTH or \
                    e.code == CtapError.ERR.PIN_POLICY_VIOLATION:
                return failure('too long')
            if e.code == CtapError.ERR.PIN_INVALID:
                return failure('wrong pin')
            if e.code == CtapError.ERR.PIN_AUTH_BLOCKED:
                return failure('currently blocked')
            if e.code == CtapError.ERR.PIN_BLOCKED:
                return failure('blocked')
            raise

    def fido_verify_pin(self, pin):
        try:
            with self._open_device([FidoConnection]) as conn:
                ctap2 = Ctap2(conn)
                client_pin = ClientPin(ctap2)
                token = client_pin.get_pin_token(pin, ClientPin.PERMISSION.CREDENTIAL_MGMT)
                self._pin = pin
                credman = CredentialManagement(ctap2, client_pin.protocol, token)
                credentials = []
                for rp in credman.enumerate_rps():
                    for cred in credman.enumerate_creds(rp[CredentialManagement.RESULT.RP_ID_HASH]):
                        logger.debug(rp[CredentialManagement.RESULT.RP]["id"])
                        logger.debug(cred[CredentialManagement.RESULT.USER]["id"].hex())
                        logger.debug(cred[CredentialManagement.RESULT.USER]["name"])
                        credentials.append({
                            'rpId': rp[CredentialManagement.RESULT.RP]["id"],
                            'userId': cred[CredentialManagement.RESULT.USER]["id"].hex(),
                            'name': cred[CredentialManagement.RESULT.USER]["name"]
                        })
                return success({'credentials': credentials})
        except CtapError as e:
            if e.code == CtapError.ERR.INVALID_LENGTH or \
                    e.code == CtapError.ERR.PIN_POLICY_VIOLATION:
                return failure('too long')
            if e.code == CtapError.ERR.PIN_INVALID:
                return failure('wrong pin')
            if e.code == CtapError.ERR.PIN_AUTH_BLOCKED:
                return failure('currently blocked')
            if e.code == CtapError.ERR.PIN_BLOCKED:
                return failure('blocked')
            raise

    def fido_reset(self):
        try:
            with self._open_device([FidoConnection]) as conn:
                ctap2 = Ctap2(conn)
                ctap2.reset()
                return success()
        except CtapError as e:
            if e.code == CtapError.ERR.NOT_ALLOWED:
                return failure('not allowed')
            if e.code == CtapError.ERR.USER_ACTION_TIMEOUT:
                return failure('touch timeout')
            raise

    def fido_cred_delete(self, userId):
        try:
            with self._open_device([FidoConnection]) as conn:
                pin = self._pin
                ctap2 = Ctap2(conn)
                client_pin = ClientPin(ctap2)
                token = client_pin.get_pin_token(pin, ClientPin.PERMISSION.CREDENTIAL_MGMT)
                self._pin = pin
                credman = CredentialManagement(ctap2, client_pin.protocol, token)
                for rp in credman.enumerate_rps():
                    for cred in credman.enumerate_creds(rp[CredentialManagement.RESULT.RP_ID_HASH]):
                        if (userId == cred[CredentialManagement.RESULT.USER]["id"].hex()):
                            credId = cred[CredentialManagement.RESULT.CREDENTIAL_ID]
                            credman.delete_cred(credId)
                            return success()
                return failure()
        except CtapError as e:
            if e.code == CtapError.ERR.INVALID_LENGTH or \
                    e.code == CtapError.ERR.PIN_POLICY_VIOLATION:
                return failure('too long')
            if e.code == CtapError.ERR.PIN_INVALID:
                return failure('wrong pin')
            if e.code == CtapError.ERR.PIN_AUTH_BLOCKED:
                return failure('currently blocked')
            if e.code == CtapError.ERR.PIN_BLOCKED:
                return failure('blocked')
            raise

    def bio_verify_pin(self, pin):
        try:
            with self._open_device([FidoConnection]) as conn:
                ctap2 = Ctap2(conn)
                client_pin = ClientPin(ctap2)
                bio = client_pin.get_pin_token(pin, ClientPin.PERMISSION.BIO_ENROLL)
                self._pin = pin
                bio = FPBioEnrollment(ctap2, client_pin.protocol, bio)
                fingerprints = []
                for t_id, name in bio.enumerate_enrollments().items():
                    fingerprints.append({
                        'id': t_id.hex(),
                        'name': name
                    })
                return success({'fingerprints': fingerprints})
        except CtapError as e:
            if e.code == CtapError.ERR.INVALID_LENGTH or \
                    e.code == CtapError.ERR.PIN_POLICY_VIOLATION:
                return failure('too long')
            if e.code == CtapError.ERR.PIN_INVALID:
                return failure('wrong pin')
            if e.code == CtapError.ERR.PIN_AUTH_BLOCKED:
                return failure('currently blocked')
            if e.code == CtapError.ERR.PIN_BLOCKED:
                return failure('blocked')
            raise

    def bio_enroll(self):
        def enroll_action(conn, bio, event):
            try:
                enroller = bio.enroll()
                while not event.is_set():
                    try:
                        logger.debug("Place your finger against the sensor now...")
                        template_id = enroller.capture(event=event)
                        if template_id:
                            pyotherside.send("bio_enroll", True, enroller.remaining, template_id.hex())
                            break
                        pyotherside.send("bio_enroll", True, enroller.remaining, 0)
                    except CaptureError as e:
                        logger.debug(f"Scan failed: {e}")
                        logger.debug(f"{enroller.remaining} more scans needed.")
                        pyotherside.send("bio_enroll", False, enroller.remaining, 0)
            except CtapError as e:
                logger.debug(f"Capture failed: {e}")
                pyotherside.send("bio_enroll", False, 0, 0)
            finally:
                conn.close()
                logger.debug("Capture complete.")

        try:
            pin = self._pin
            conn = self._open_device([FidoConnection])
            ctap2 = Ctap2(conn)
            client_pin = ClientPin(ctap2)
            token = client_pin.get_pin_token(pin, ClientPin.PERMISSION.BIO_ENROLL)
            bio = FPBioEnrollment(ctap2, client_pin.protocol, token)

            self._event = Event()
            Thread(target=enroll_action, args=(conn, bio, self._event)).start()
            return success()
        except CtapError as e:
            conn.close()
            if e.code == CtapError.ERR.PIN_AUTH_BLOCKED:
                return failure('PIN authentication is currently blocked. '
                               'Remove and re-insert the YubiKey.')
            if e.code == CtapError.ERR.PIN_BLOCKED:
                return failure('PIN is blocked.')
            raise

    def bio_enroll_cancel(self):
        if self._event:
            self._event.set()
            self._event = None

    def reset_cancel(self):
        if self._event:
            self._event.set()
            self._event = None

    def bio_delete(self, template_id):
        try:
            pin = self._pin
            with self._open_device([FidoConnection]) as conn:
                ctap2 = Ctap2(conn)
                client_pin = ClientPin(ctap2)
                token = client_pin.get_pin_token(pin, ClientPin.PERMISSION.BIO_ENROLL)
                bio = FPBioEnrollment(ctap2, client_pin.protocol, token)

                enrollments = bio.enumerate_enrollments()
                try:
                    key: Optional[bytes] = bytes.fromhex(template_id)
                except ValueError:
                    key = None

                if key not in enrollments:
                    # Match using template_id as NAME
                    matches = [k for k in enrollments if enrollments[k] == template_id]
                    if len(matches) == 0:
                        logger.debug(f"No fingerprint matching ID={template_id}")
                    elif len(matches) > 1:
                        logger.debug(
                            f"Multiple matches for NAME={template_id}. "
                            "Delete by template ID instead."
                        )
                        return failure("multiple_matches")
                    key = matches[0]

                name = enrollments[key]

                try:
                    bio.remove_enrollment(key)
                    return success()
                except:
                    logger.debug("Failed to delete")
        except CtapError as e:
            if e.code == CtapError.ERR.PIN_AUTH_BLOCKED:
                return failure('PIN authentication is currently blocked. '
                               'Remove and re-insert the YubiKey.')
            if e.code == CtapError.ERR.PIN_BLOCKED:
                return failure('PIN is blocked.')
            raise

    def bio_rename(self, template_id, name):
        try:
            pin = self._pin
            with self._open_device([FidoConnection]) as conn:
                ctap2 = Ctap2(conn)
                client_pin = ClientPin(ctap2)
                token = client_pin.get_pin_token(pin, ClientPin.PERMISSION.BIO_ENROLL)
                bio = FPBioEnrollment(ctap2, client_pin.protocol, token)

                enrollments = bio.enumerate_enrollments()

                key = bytes.fromhex(template_id)
                if key not in enrollments:
                    logger.debug(f"No fingerprint matching ID={template_id}.")
                logger.debug("Fingerprint renamed")
                bio.set_name(key, name)
                return success()
        except CtapError as e:
            if e.code == CtapError.ERR.PIN_AUTH_BLOCKED:
                return failure('PIN authentication is currently blocked. '
                               'Remove and re-insert the YubiKey.')
            if e.code == CtapError.ERR.PIN_BLOCKED:
                return failure('PIN is blocked.')
            raise



class PixelImage(object):

    def __init__(self, data, width, height):
        self.data = data
        self.width = width
        self.height = height

    def get_line(self, line_number):
        return self.data[
            self.width * line_number:self.width * (line_number + 1)]


controller = None


def init_with_logging(log_level, log_file=None):
    logging_setup = as_json(ykman.logging_setup.setup)
    logging_setup(log_level, log_file)
    init()


def init():
    global controller
    controller = Controller()
