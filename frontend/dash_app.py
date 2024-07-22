from app import cache
from dash import Dash, html, dcc, Input, Output
from flask import Flask
from typing import Dict, Any


def create_dash_app(flask_app):
    dash_app = Dash(__name__, server=flask_app, url_base_pathname='/dash/')

    @dash_app.callback(Output('user-info', 'children'),
                       Input('interval-component', 'n_intervals'))
    def update_user_info(n):
        user_data = cache.get('user_data')
        if user_data:
            return f"Welcome, {user_data['name']}! Your stocks: {', '.join(user_data['stocks'])}"
        return "Welcome! No user data available."

    dash_app.layout = html.Div([
        html.Div(id='user-info'),
        dcc.Interval(id='interval-component', interval=1*1000, n_intervals=0),
        # Rest of your Dash layout
    ])

    return dash_app
