#!/bin/bash
# Stops the Pokémon restock monitor on this Mac.
launchctl bootout "gui/$(id -u)/com.pokemon.restock" >/dev/null 2>&1 || true
rm -f "$HOME/Library/LaunchAgents/com.pokemon.restock.plist"
echo "🛑 Pokémon restock monitor stopped. (Files are still in ~/pokemon-restock – delete that folder to remove everything.)"
