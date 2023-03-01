import QtQuick 2.9
import QtQuick.Controls 2.2
import QtQuick.Layouts 1.3
import QtQuick.Controls.Material 2.2

Pane {

    id: expansionPanel

    default property alias children: inner_space.data

    property string label
    property string description
    property string metadata
    property string backgroundColor: defaultBackground
    property string searchQuery: toolBar.searchField.text
    property string searchText: label.concat(":", description, ":", metadata)

    property bool isFlickable: false
    property bool isEnabled: true
    property bool isExpanded: false
    property bool isTopPanel: false
    property bool isBottomPanel: false
    property bool isVisible: true
    property bool dropShadow: false

    property string toolButtonIcon
    property string toolButtonToolTip
    property alias toolButton: toolButton
    property alias actionButton: actionButton
    property alias expandButton: expandButton
    property alias expandedContent: expandedContent
    property int expandedPadding: isEnabled ? 48 : 19

    Layout.alignment: Qt.AlignCenter | Qt.AlignTop
    Layout.fillWidth: true
    Layout.minimumHeight: isExpanded ? panelHeader.height + expandedContent.height + expandedPadding : panelHeader.height + 16

    Layout.leftMargin: -12
    Layout.rightMargin: -12

    Layout.topMargin: isExpanded && dropShadow && !isTopPanel ? 9 : -4
    Layout.bottomMargin: isExpanded && dropShadow && !isBottomPanel ? 11 : -3
    bottomPadding: panelDescription.lineCount > 1 ? 8 : 6

    Material.background: backgroundColor
    Material.elevation: dropShadow ? 1 : 0
    visible: searchQuery.length > 0 ? isVisible && searchText.match(escapeRegExp(searchQuery, "i")) : isVisible

    activeFocusOnTab: true

    function expandAction() {
        if (isEnabled && !isFlickable) {
            if (isExpanded) {
                isExpanded = false
            } else {
                isExpanded = true
            }
        }
    }

    ColumnLayout {
        x: 16
        Layout.alignment: Qt.AlignLeft | Qt.AlignTop
        width: parent.width - dynamicMargin
        spacing: isEnabled ? 16 : 0

        RowLayout {
            Layout.leftMargin: -12
            Layout.rightMargin: -24
            id: panelHeader

            ColumnLayout {
                Layout.fillHeight: true
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignLeft | (description ? Qt.AlignTop : Qt.AlignVCenter)
                Layout.topMargin: 0
                Layout.bottomMargin: 0
                visible: label
                spacing: 0

                Label {
                    text: searchQuery.length > 0 ? colorizeMatch(label, searchQuery) : label
                    textFormat: TextEdit.RichText
                    font.pixelSize: 13
                    font.bold: false
                    color: primaryColor
                    opacity: enabled ? highEmphasis : disabledEmphasis
                    Layout.fillWidth: true
                    Layout.bottomMargin: 4
                }
                Label {
                    id: panelDescription
                    Layout.alignment: Qt.AlignLeft | Qt.AlignTop
                    Layout.fillWidth: true
                    font.pixelSize: 13
                    color: primaryColor
                    opacity: enabled ? lowEmphasis : disabledEmphasis
                    text: searchQuery.length > 0 ? colorizeMatch(description, searchQuery) : description
                    textFormat: searchQuery.length > 0 ? TextEdit.RichText : TextEdit.PlainText
                    wrapMode: Text.WordWrap
                    maximumLineCount: isExpanded ? 4 : 2
                    elide: Text.ElideRight
                    visible: description
                }
            }

            ToolButton {
                id: expandButton
                Layout.alignment: Qt.AlignHCenter | Qt.AlignTop
                onClicked: expandAction()
                icon.width: 24
                icon.source: isFlickable ? "../images/next.svg" : (isExpanded ? "../images/up.svg" : "../images/down.svg")
                icon.color: primaryColor
                opacity: hovered ? fullEmphasis : (enabled ? lowEmphasis : disabledEmphasis)
                visible: isEnabled
                focus: true
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    enabled: false
                }
            }

            ToolButton {
                id: toolButton
                icon.width: 20
                icon.height: 20
                icon.source: toolButtonIcon
                icon.color: primaryColor
                opacity: hovered ? fullEmphasis : (enabled ? lowEmphasis : disabledEmphasis)
                visible: !isEnabled && !!toolButtonIcon
                enabled: expansionPanel.enabled
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    enabled: false
                }
                ToolTip {
                    text: toolButtonToolTip
                    delay: 1000
                    parent: toolButton
                    visible: parent.hovered
                    Material.foreground: toolTipForeground
                    Material.background: toolTipBackground
                }
            }

            StyledButton {
                id: actionButton
                visible: text.length > 0
                Layout.alignment: Qt.AlignRight | Qt.AlignTop
                Layout.rightMargin: 12
            }
        }

        RowLayout {
            id: expandedContent
            visible: isExpanded
            Layout.leftMargin: -12
            Layout.rightMargin: -12
            ColumnLayout {
                id: inner_space
            }
        }
    }
}
