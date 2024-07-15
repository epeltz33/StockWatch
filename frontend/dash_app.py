from dash import Dash
import dash_bootstrap_components as dbc
from flask import Flask

server = Flask(__name__)
app = Dash(__name__, server=server,
           external_stylesheets=[dbc.themes.BOOTSTRAP])


def set_layout(layout):
    app.layout = layout

# Export server for running


def get_server():
    return server
