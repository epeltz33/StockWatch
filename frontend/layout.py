import dash_core_components as dcc
import dash_html_components as html
from frontend.components.navbar import navbar

layout = html.Div([
    navbar,
    html.Div(id='page-content')
])