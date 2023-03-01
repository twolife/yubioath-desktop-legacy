import QtQuick 2.9
import QtQuick.Controls 2.2
import QtQuick.Layouts 1.3
import QtQuick.Controls.Material 2.2

Flickable {

    id: fingerPrintsView
    objectName: 'fingerPrintsViewFlickable'
    contentWidth: app.width
    contentHeight: content.height + dynamicMargin

    property var fidoPinCache: !!yubiKey.currentDevice && yubiKey.currentDevice.fidoPinCache ? yubiKey.currentDevice.fidoPinCache : ""

    property var currentDevice: yubiKey.currentDevice
    property bool yubiKeyRemoved: yubiKey.availableDevices.length === 0

    onContentHeightChanged: {
        if (contentHeight > app.height - toolBar.height) {
             scrollBar.active = true
         }
    }

    onCurrentDeviceChanged: {
        if(focus) {
            navigator.goToYubiKey()
        }
    }

    onYubiKeyRemovedChanged: {
        navigator.goToYubiKey()
    }

    onFocusChanged: {
        if(fingerPrintsView.focus) {
            yubiKey.bioVerifyPin(fidoPinCache, function(resp) {
                if (resp.success) {
                    yubiKey.fingerprints = resp.fingerprints
                }
            })
        }
    }

    ScrollBar.vertical: ScrollBar {
        id: scrollBar
        width: 8
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        hoverEnabled: true
        z: 2
    }
    boundsBehavior: Flickable.StopAtBounds

    property string searchFieldPlaceholder: ""

    ColumnLayout {
        id: content
        spacing: 0

        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        width: app.width < dynamicWidth
               ? app.width
               : dynamicWidth

        ColumnLayout {
            width: content.width - 32
            Layout.leftMargin: 16
            Layout.rightMargin: 16

            Label {
                text: "Fingerprints"
                font.pixelSize: 16
                font.weight: Font.Normal
                color: yubicoGreen
                opacity: fullEmphasis
                Layout.topMargin: 24
                Layout.bottomMargin: 24
                Layout.fillWidth: true
            }

            Label {
                text: yubiKey.fingerprints.length > 0 ? qsTr("Fingerprints on this YubiKey") : qsTr("There are no fingerprints on this YubiKey")
                color: primaryColor
                opacity: lowEmphasis
                font.pixelSize: 13
                lineHeight: 1.2
                textFormat: TextEdit.PlainText
                wrapMode: Text.WordWrap
                Layout.maximumWidth: parent.width
                Layout.bottomMargin: 16
            }

            Repeater {
                model: yubiKey.fingerprints
                id: fingerprintRepeater

                RowLayout {
                    spacing: 0
                    StyledTextField {
                        text: modelData.name ? modelData.name : qsTr("Unnamed (ID: %1)").arg(modelData.id)
                        textField.font.italic: modelData.name ? false : true
                        isEnabled: false
                        noedit: true
                        Layout.bottomMargin: -8

                        RowLayout {
                            anchors.right: parent.right
                            ToolButton {
                                Layout.alignment: Qt.AlignRight | Qt.AlignTop

                                onClicked: navigator.confirmInput({
                                    "promptMode": true,
                                    "maximumLength": 15,
                                    "heading": qsTr("Rename fingerprint"),
                                    "text1": qsTr("Enter a name for this fingerprint"),
                                    "promptText": qsTr("Name"),
                                    "promptCurrent": modelData.name ? modelData.name : "",
                                    "acceptedCb": function(resp) {
                                        yubiKey.bioRename(modelData.id, resp, function (resp_inner) {
                                           if (resp_inner.success) {
                                                var item = yubiKey.fingerprints.find(item => item.id === modelData.id);
                                                if (item) {
                                                    item.name = resp;
                                                }
                                                yubiKey.fingerprints = yubiKey.fingerprints
                                           } else {
                                                navigator.snackBarError(qsTr("Fingerprint not renamed"))
                                           }
                                       })
                                    }
                                })

                                icon.source: "../images/edit.svg"
                                icon.color: primaryColor
                                opacity: hovered ? highEmphasis : disabledEmphasis
                                implicitHeight: 30
                                implicitWidth: 30

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    propagateComposedEvents: true
                                    enabled: false
                                }
                            }

                            ToolButton {
                                Layout.alignment: Qt.AlignRight | Qt.AlignTop

                                onClicked: navigator.confirm({
                                    "heading": qsTr("Delete " + (modelData.name ? modelData.name : modelData.id) + " ?"),
                                    "message": qsTr("Fingerprint will be removed from YubiKey."),
                                    "buttonAccept": qsTr("Delete"),
                                    "acceptedCb": function () {
                                        yubiKey.bioDelete(modelData.id, function (resp) {
                                           if (resp.success) {
                                                yubiKey.fingerprints = yubiKey.fingerprints.filter(item => item.id !== modelData.id)
                                           } else {
                                               if (resp.error_id === "multiple_matches") {
                                                   navigator.snackBarError(qsTr("Multiple matches."))
                                               } else {
                                                   navigator.snackBarError(qsTr("Fingerprint not deleted"))
                                               }
                                           }
                                       })
                                    }
                                })

                                icon.source: "../images/delete.svg"
                                icon.color: primaryColor
                                opacity: hovered ? highEmphasis : disabledEmphasis
                                implicitHeight: 30
                                implicitWidth: 30

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    propagateComposedEvents: true
                                    enabled: false
                                }
                            }
                        }
                    }

                }
            }

            StyledButton {
                text: qsTr("Add")
                enabled: yubiKey.fingerprints.length < 5
                primary: true
                Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                Layout.topMargin: 16
                onClicked: navigator.goToNewFingerPrintView()
                Keys.onEnterPressed: navigator.goToNewFingerPrintView()
                Keys.onReturnPressed: navigator.goToNewFingerPrintView()
            }
        }
    }
}
