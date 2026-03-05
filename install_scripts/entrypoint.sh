#!/bin/bash
set -e 

echo "Container initializing."

if [ "$ENABLE_C_FAMILY" = "true" ]; then
    echo "Install uncrustify."
    source "$(dirname "$0")/install_uncrustify.sh"
fi

if [ "$ENABLE_JS_TS" = "true" ]; then
    echo "Install Babel packages."
    source "$(dirname "$0")/install_babel.sh"
fi

if [ "$ENABLE_GUESS_LANG" = "true" ]; then
    echo "Install tensorflow"
    source "$(dirname "$0")/install_tensorflow.sh" 
fi

if [ "$ENABLE_GO" = "true" ]; then
    echo "Install Go."
    source "$(dirname "$0")/install_go.sh" 
fi


echo "Initialization complete. Starting Main App."

# run main container command
exec "$@"