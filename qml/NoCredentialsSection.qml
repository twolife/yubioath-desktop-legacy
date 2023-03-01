import QtQuick 2.9
import QtQuick.Controls 2.2
import QtQuick.Layouts 1.3
import QtQuick.Controls.Material 2.2

ColumnLayout {

    anchors.horizontalCenter: parent.horizontalCenter
    anchors.verticalCenter: parent.verticalCenter

    ColumnLayout {
        Layout.alignment: Qt.AlignHCenter | Qt.AlignVCenter
        Layout.bottomMargin: 16

        StyledImage {
            source: "../images/people.svg"
            color: defaultImageOverlay
            iconWidth: 80
            Layout.alignment: Qt.AlignHCenter | Qt.AlignVCenter
        }

        Label {
            text: qsTr("No accounts")
            Layout.rowSpan: 1
            wrapMode: Text.WordWrap
            font.pixelSize: 16
            font.weight: Font.Normal
            lineHeight: 1.5
            Layout.alignment: Qt.AlignHCenter | Qt.AlignVCenter
            color: primaryColor
            opacity: highEmphasis
        }

        Label {
            text: qsTr("Add accounts to this YubiKey in order to generate security codes.")
            horizontalAlignment: Qt.AlignHCenter
            Layout.minimumWidth: 300
            Layout.maximumWidth: app.width - dynamicMargin
                                 < dynamicWidthSmall ? app.width - dynamicMargin : dynamicWidthSmall
            Layout.rowSpan: 1
            lineHeight: 1.1
            wrapMode: Text.WordWrap
            font.pixelSize: 13
            Layout.alignment: Qt.AlignHCenter | Qt.AlignVCenter
            color: primaryColor
            opacity: lowEmphasis
        }

        StyledButton {
            id: addBtn
            text: qsTr("Add account")
            enabled: true
            focus: true
            Layout.alignment: Qt.AlignCenter | Qt.AlignVCenter
            onClicked: navigator.goToNewCredential()
            Keys.onReturnPressed: navigator.goToNewCredential()
            Keys.onEnterPressed: navigator.goToNewCredential()
            Layout.topMargin: 8
        }
    }
}
