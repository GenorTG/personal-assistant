#!/bin/bash
# Cross-platform launcher menu for Personal Assistant
# Works on Linux (uses zenity/kdialog) and falls back to terminal menu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

show_menu() {
    # Try GUI dialogs first (Linux)
    if command -v zenity &> /dev/null; then
        choice=$(zenity --list \
            --title="Personal Assistant" \
            --text="Choose an action:" \
            --column="Action" \
            "Install" \
            "Update and Start" \
            "Start" \
            "Exit" \
            --width=400 \
            --height=250)
        
        if [ -z "$choice" ]; then
            exit 0
        fi
        
        case "$choice" in
            "Install")
                gnome-terminal --title="Personal Assistant - Installation" -- bash -c "cd '$SCRIPT_DIR' && ./install.sh; echo ''; echo 'Press Enter to close...'; read" 2>/dev/null || \
                xterm -title "Personal Assistant - Installation" -e "bash -c 'cd \"$SCRIPT_DIR\" && ./install.sh; echo \"\"; echo \"Press Enter to close...\"; read'" 2>/dev/null || \
                konsole --title "Personal Assistant - Installation" -e "bash -c 'cd \"$SCRIPT_DIR\" && ./install.sh; echo \"\"; echo \"Press Enter to close...\"; read'" 2>/dev/null || \
                exec ./install.sh
                ;;
            "Update and Start")
                gnome-terminal --title="Personal Assistant - Update and Start" -- bash -c "cd '$SCRIPT_DIR' && ./update-and-start.sh; echo ''; echo 'Press Enter to close...'; read" 2>/dev/null || \
                xterm -title "Personal Assistant - Update and Start" -e "bash -c 'cd \"$SCRIPT_DIR\" && ./update-and-start.sh; echo \"\"; echo \"Press Enter to close...\"; read'" 2>/dev/null || \
                konsole --title "Personal Assistant - Update and Start" -e "bash -c 'cd \"$SCRIPT_DIR\" && ./update-and-start.sh; echo \"\"; echo \"Press Enter to close...\"; read'" 2>/dev/null || \
                exec ./update-and-start.sh
                ;;
            "Start")
                exec ./start.sh
                ;;
            "Exit")
                exit 0
                ;;
        esac
    elif command -v kdialog &> /dev/null; then
        choice=$(kdialog --menu "Personal Assistant - Choose an action:" \
            "1" "Install" \
            "2" "Update and Start" \
            "3" "Start" \
            "4" "Exit")
        
        case "$choice" in
            "1")
                exec ./install.sh
                ;;
            "2")
                exec ./update-and-start.sh
                ;;
            "3")
                exec ./start.sh
                ;;
            "4"|"")
                exit 0
                ;;
        esac
    else
        # Fallback to terminal menu
        echo ""
        echo "=========================================="
        echo "Personal Assistant"
        echo "=========================================="
        echo ""
        echo "Choose an action:"
        echo "  1) Install"
        echo "  2) Update and Start"
        echo "  3) Start"
        echo "  4) Exit"
        echo ""
        read -p "Enter choice [1-4]: " choice
        
        case "$choice" in
            1)
                exec ./install.sh
                ;;
            2)
                exec ./update-and-start.sh
                ;;
            3)
                exec ./start.sh
                ;;
            4|*)
                exit 0
                ;;
        esac
    fi
}

show_menu
