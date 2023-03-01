import QtQuick 2.9
import QtQuick.Controls 2.2
import QtQuick.Layouts 1.3
import QtQuick.Controls.Material 2.2

Flickable {

    id: settingsPanel
    objectName: 'newFingerPrintViewFlickable'
    contentWidth: app.width
    contentHeight: content.height + dynamicMargin
    StackView.onActivating: enroll()

    property var last_template
    property var currentDevice: yubiKey.currentDevice

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

    Timer {
        id: touchFeedback
        interval: 250
        onTriggered: {
            fingerprintIcon.color = primaryColor
            fingerprintIcon.opacity = lowEmphasis
        }
    }

    ColumnLayout {
        id: content
        spacing: 0

        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        width: app.width - dynamicMargin < dynamicWidth
               ? app.width - dynamicMargin
               : dynamicWidth

        ColumnLayout {
            width: content.width

            Label {
                text: "Add fingerprint"
                font.pixelSize: 16
                font.weight: Font.Normal
                color: yubicoGreen
                opacity: fullEmphasis
                Layout.topMargin: 24
                Layout.bottomMargin: 24
                Layout.fillWidth: true
            }

            Label {
                text: progressBar.value > 0 ? qsTr("Keep touching your YubiKey until your fingerprint is captured") : qsTr("Touch your YubiKey to capture your fingerprint")
                color: primaryColor
                opacity: lowEmphasis
                font.pixelSize: 13
                lineHeight: 1.2
                textFormat: TextEdit.PlainText
                wrapMode: Text.WordWrap
                Layout.maximumWidth: parent.width
                Layout.bottomMargin: 32
            }

            StyledImage {
                id: fingerprintIcon
                source: "../images/fingerprint.svg"
                color: primaryColor
                opacity: lowEmphasis
                iconWidth: 150
                Layout.alignment: Qt.AlignHCenter | Qt.AlignVCenter
                bottomPadding: 32
            }

            ProgressBar {
                id: progressBar
                value: 0
                Layout.fillWidth: true
                Layout.bottomMargin: 32
            }

            StyledButton {
                text: qsTr("Cancel")
                Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                visible: progressBar.value < 1
                primary: false
                onClicked: enroll_cancel()
                Keys.onEnterPressed: click()
                Keys.onReturnPressed: click()
            }

            StyledButton {
                text: qsTr("Continue")
                visible: progressBar.value === 1
                Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                primary: true
                onClicked: navigator.confirmInput({
                    "promptMode": true,
                    "maximumLength": 15,
                    "heading": qsTr("Add fingerprint"),
                    "text1": qsTr("Enter a name for this fingerprint"),
                    "promptText": qsTr("Name"),
                    "acceptedCb": function(resp) {
                        yubiKey.bioRename(last_template, resp, function (resp_inner) {
                            if (!resp_inner.success) {
                                console.log("error renaming fingerprint")
                            }
                        })
                        navigator.pop()
                        navigator.snackBar(qsTr("Fingerprint added"))
                    }
                })
                Keys.onEnterPressed: click()
                Keys.onReturnPressed: click()
            }

        }
    }

    function enroll(){
        yubiKey.bioEnroll(function (success, remaining, template) {
            if (success) {
                fingerprintIcon.color = yubicoGreen
                fingerprintIcon.opacity = highEmphasis
                if (remaining > 0) {
                    touchFeedback.start()
                    progressBar.value = progressBar.value + 0.2
                } else {
                    progressBar.value = 1
                    last_template = template
                }
            } else {
                fingerprintIcon.color = yubicoRed
                fingerprintIcon.opacity = highEmphasis
                touchFeedback.start()
                if (remaining == 0) {
                    navigator.pop()
                }
            }
        })

    }

    function enroll_cancel() {
        yubiKey.bioEnrollCancel()
    }
}
