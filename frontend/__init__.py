import frontend.callbacks
from .dash_app import app, server, set_layout
from frontend.layout import create_layout

# Set the layout
set_layout(create_layout())

# Import and register callbacks
