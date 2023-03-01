import QtQuick 2.9
import QtQuick.Controls 2.2
import QtQuick.Layouts 1.3
import QtQuick.Controls.Material 2.2
import Qt.labs.platform 1.1 as PopUpMenu

ToolBar {
    id: toolBar

    background: Rectangle {
        color: defaultBackground
        opacity: 0.9
    }

    width: app.width

    function getToolbarColor(isActive) {
        if (!isActive) {
            return 0
        } else {
            return 0.05
        }
    }

    property alias drawerBtn: drawerBtn
    property alias searchField: searchField
    property alias moreBtn: moreBtn
    property alias backBtn: backBtn

    property string searchFieldPlaceholder: !!navigator.currentItem ? navigator.currentItem.searchFieldPlaceholder || "" : ""

    RowLayout {
        spacing: 0
        anchors.fill: parent
        visible: !navigator.isInLoading()
        Layout.alignment: Qt.AlignTop

        ToolButton {
            id: drawerBtn
            Layout.alignment: Qt.AlignLeft | Qt.AlignVCenter
            Layout.leftMargin: 4
            visible: !navigator.isInLoading() && !navigator.isInFlickable()

            onClicked: drawer.toggle()
            Keys.onReturnPressed: drawer.toggle()
            Keys.onEnterPressed: drawer.toggle()

            KeyNavigation.left: navigator
            KeyNavigation.backtab: navigator
            KeyNavigation.right: searchField.visible ? searchField : (closeBtn.visible ? closeBtn : moreBtn)
            KeyNavigation.tab: searchField.visible ? searchField : (closeBtn.visible ? closeBtn : moreBtn)

            Accessible.role: Accessible.Button
            Accessible.name: "Menu"
            Accessible.description: "Menu button"

            icon.source: "../images/menu.svg"
            icon.color: primaryColor
            opacity: hovered ? fullEmphasis : lowEmphasis

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                enabled: false
            }
        }

        ToolButton {
            id: backBtn
            Layout.alignment: Qt.AlignLeft | Qt.AlignVCenter
            Layout.leftMargin: 4
            visible: !navigator.isInLoading() && navigator.isInFlickable()

            onClicked: ifFingerprintBack()
            Keys.onReturnPressed: ifFingerprintBack()
            Keys.onEnterPressed: ifFingerprintBack()

            KeyNavigation.left: navigator
            KeyNavigation.backtab: navigator
            KeyNavigation.right: navigator
            KeyNavigation.tab: navigator

            Accessible.role: Accessible.Button
            Accessible.name: "Back"
            Accessible.description: "Back button"

            icon.source: "../images/back.svg"
            icon.color: primaryColor
            opacity: hovered ? fullEmphasis : lowEmphasis

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                enabled: false
            }

            function ifFingerprintBack() {
                if (navigator.isInNewFingerprint()) {
                    yubiKey.bioEnrollCancel()
                } else {
                    navigator.pop()
                }
            }
        }

        ToolButton {
            id: searchBtn
            visible: searchField.placeholderText != ""
            Layout.minimumHeight: 30
            Layout.maximumHeight: 30
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignLeft | Qt.AlignVCenter
            background: Rectangle {
                color: primaryColor
                opacity: getToolbarColor(searchBtn.hovered)
                height: 30
                radius: 4
            }

            TextField {
                id: searchField
                visible: parent.visible
                selectByMouse: true
                selectedTextColor: fullContrast
                Layout.fillWidth: true
                Layout.fillHeight: true
                placeholderText: searchFieldPlaceholder
                placeholderTextColor: formText
                leftPadding: 28
                rightPadding: 8
                width: parent.width
                horizontalAlignment: Qt.AlignLeft
                verticalAlignment: Qt.AlignVCenter
                color: primaryColor
                opacity: hovered || activeFocus ? fullEmphasis : lowEmphasis
                background: Rectangle {
                    color: primaryColor
                    height: 30
                    radius: 4
                    opacity: getToolbarColor(searchField.focus)
                }

                Accessible.role: Accessible.EditableText
                Accessible.searchEdit: true
                onTextChanged: forceActiveFocus()
                onVisibleChanged: {
                    if (!visible) {
                        exitSearchMode(true)
                    }
                }
                MouseArea {
                    anchors.fill: parent
                    acceptedButtons: Qt.RightButton
                    hoverEnabled: true
                    cursorShape: Qt.IBeamCursor
                    onClicked: {
                        contextMenu.open();
                    }
                    onPressAndHold: {
                        if (mouse.source === Qt.MouseEventNotSynthesized) {
                            contextMenu.open();
                        }
                    }
                }

                PopUpMenu.Menu {
                    id: contextMenu

                    PopUpMenu.MenuItem {
                        text: qsTr("Cut")
                        onTriggered: {
                            searchField.cut()
                        }
                    }
                    PopUpMenu.MenuItem {
                        text: qsTr("Copy")
                        onTriggered: {
                            searchField.copy()
                        }
                    }
                    PopUpMenu.MenuItem {
                        text: qsTr("Paste")
                        onTriggered: {
                            searchField.paste()
                        }
                    }
                }

                function exitSearchMode(clearInput) {
                    if (clearInput) {
                        text = ""
                    }
                    focus = false
                    navigator.forceActiveFocus()
                }

                KeyNavigation.backtab: drawerBtn
                KeyNavigation.left: drawerBtn
                KeyNavigation.tab: moreBtn.visible ? moreBtn : navigator
                KeyNavigation.right: moreBtn.visible ? moreBtn : navigator
                Keys.onEscapePressed: exitSearchMode(true)
                Keys.onDownPressed: exitSearchMode(false)
                Keys.onReturnPressed: {
                    if (navigator.hasSelectedOathCredential()) {
                        navigator.oathCopySelectedCredential()
                    }
                }
                Keys.onEnterPressed: {
                    if (navigator.hasSelectedOathCredential()) {
                        navigator.oathCopySelectedCredential()
                    }
                }

                StyledImage {
                    id: searchIcon
                    x: 5
                    y: 6
                    iconHeight: 20
                    iconWidth: 20
                    source: "../images/search.svg"
                    color: primaryColor
                    opacity: searchField.hovered || searchField.activeFocus ? fullEmphasis : lowEmphasis

                }
            }
        }

        RowLayout {
            spacing: 0
            Layout.alignment: Qt.AlignRight | Qt.AlignVCenter

            ToolButton {
                id: closeBtn
                activeFocusOnTab: true
                Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                visible: navigator.isInNewOathCredential() || navigator.isInApplications()
                onClicked: navigator.pop(StackView.Immediate)
                icon.source: "../images/clear.svg"
                icon.color: primaryColor
                opacity: hovered ? fullEmphasis : lowEmphasis

                Keys.onReturnPressed: navigator.pop(StackView.Immediate)
                Keys.onEnterPressed: navigator.pop(StackView.Immediate)

                KeyNavigation.left: drawerBtn
                KeyNavigation.backtab: drawerBtn
                KeyNavigation.right: navigator
                KeyNavigation.tab: navigator

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    enabled: false
                }
            }

            ToolButton {
                id: moreBtn
                activeFocusOnTab: true
                Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                visible: navigator.isInAuthenticator() || navigator.isInEnterPassword() || navigator.isInYubiKeyView()
                icon.source: "../images/more.svg"
                icon.color: primaryColor
                opacity: hovered ? fullEmphasis : lowEmphasis

                onClicked: navigator.isInAuthenticator() || navigator.isInEnterPassword() ? authenticatorContextMenu.open() : yubikeyContextMenu.open()
                Keys.onReturnPressed: navigator.isInAuthenticator() || navigator.isInEnterPassword() ? authenticatorContextMenu.open() : yubikeyContextMenu.open()
                Keys.onEnterPressed: navigator.isInAuthenticator() || navigator.isInEnterPassword() ? authenticatorContextMenu.open() : yubikeyContextMenu.open()

                KeyNavigation.left: searchField.visible ? searchField : drawerBtn
                KeyNavigation.backtab: searchField.visible ? searchField : drawerBtn
                KeyNavigation.right: navigator
                KeyNavigation.tab: navigator

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    enabled: false
                }

                Menu {
                    id: authenticatorContextMenu
                    y: header.height
                    MenuItem {
                        text: "Scan QR code"
                        icon.source: "../images/qr-scanner.svg"
                        icon.color: primaryColor
                        opacity: enabled ? highEmphasis : disabledEmphasis
                        icon.width: 20
                        icon.height: 20
                        onTriggered: yubiKey.scanQr()
                        enabled: !navigator.isInEnterPassword() && !!yubiKey.currentDevice && yubiKey.currentDeviceEnabled("OATH")
                    }
                    MenuItem {
                        text: "Add account"
                        icon.source: "../images/edit.svg"
                        icon.color: primaryColor
                        opacity: enabled ? highEmphasis : disabledEmphasis
                        icon.width: 20
                        icon.height: 20
                        onTriggered: navigator.goToNewCredential()
                        enabled: !navigator.isInEnterPassword() && !!yubiKey.currentDevice && yubiKey.currentDeviceEnabled("OATH")
                    }
                    MenuSeparator {}
                    MenuItem {
                        text: "Manage password"
                        icon.source: "../images/password.svg"
                        icon.color: primaryColor
                        opacity: enabled ? highEmphasis : disabledEmphasis
                        icon.width: 20
                        icon.height: 20
                        enabled: !settings.otpMode && !navigator.isInEnterPassword() && !!yubiKey.currentDevice && yubiKey.currentDeviceEnabled("OATH")
                        onTriggered: navigator.confirmInput({
                            "heading": text,
                            "manageMode": true
                        })
                    }
                    MenuItem {
                        text: "Reset defaults"
                        icon.source: "../images/reset.svg"
                        icon.color: primaryColor
                        opacity: enabled ? highEmphasis : disabledEmphasis
                        icon.width: 20
                        icon.height: 20
                        enabled: !settings.otpMode && !!yubiKey.currentDevice && yubiKey.currentDeviceEnabled("OATH")
                        onTriggered: navigator.confirm({
                            "heading": qsTr("Reset to defaults?"),
                            "message": qsTr("Warning: This action will delete all OATH TOTP/HOTP accounts and password on your YubiKey."),
                            "description": qsTr("You will not be able to generate security codes for any of your accounts. Make sure 2FA has been disabled on all web services."),
                            "buttonAccept": qsTr("Reset YubiKey"),
                            "acceptedCb": function () {
                                navigator.goToLoading()
                                yubiKey.reset(function (resp) {
                                    if (resp.success) {
                                        entries.clear()
                                        navigator.snackBar(qsTr("Reset completed"))
                                        yubiKey.currentDevice.hasPassword = false
                                    } else {
                                        navigator.snackBarError(
                                                    navigator.getErrorMessage(
                                                        resp.error_id))
                                        console.log("reset failed:",
                                                    resp.error_id)
                                        if (resp.error_id === 'no_device_custom_reader') {
                                            yubiKey.clearCurrentDeviceAndEntries()
                                        }
                                    }
                                    navigator.goToAuthenticator()
                                })
                            }
                        })
                    }
                }

                Menu {
                    id: yubikeyContextMenu
                    y: header.height
                    MenuItem {
                        text: "Toggle Applications"
                        icon.source: "../images/apps.svg"
                        icon.color: primaryColor
                        opacity: enabled ? highEmphasis : disabledEmphasis
                        icon.width: 20
                        icon.height: 20
                        enabled: !!yubiKey.currentDevice && (yubiKey.supportsNewInterfaces() || !yubiKey.currentDevice.isNfc)
                        onTriggered: {
                            if (yubiKey.availableDevices.length > 1) {
                                navigator.waitForYubiKey({
                                    "acceptedCb": function(resp) {
                                        navigator.goToApplicationsView()
                                    }
                                })
                            } else {
                                navigator.goToApplicationsView()
                            }
                        }
                    }
                }
            }
        }
    }


}
