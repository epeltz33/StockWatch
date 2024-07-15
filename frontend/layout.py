from dash import dcc
from dash import html
from frontend.components import navbar

layout = html.Div([
    navbar,
    html.Div(id='page-content')
])
