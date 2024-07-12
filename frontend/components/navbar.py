
import dash
import dash_core_components as dcc
import dash_html_components as html

# Initialize the Dash app
app = dash.Dash(__name__)

# Define the layout for the navbar
navbar = html.Div(
	[
		html.Nav(
			[
				html.A("Home", href="/", className="nav-link"),
				html.A("Page 1", href="/page-1", className="nav-link"),
				html.A("Page 2", href="/page-2", className="nav-link"),
			],
			className="navbar"
		)
	],
	className="navbar-container"
)

# Define the app layout
app.layout = html.Div(
	[
		navbar,
		dcc.Location(id='url', refresh=False),
		html.Div(id='page-content')
	]
)

# Define the callback to update the page content
@app.callback(
	dash.dependencies.Output('page-content', 'children'),
	[dash.dependencies.Input('url', 'pathname')]
)
def display_page(pathname):
	if pathname == '/page-1':
		return html.Div([html.H3('Page 1 Content')])
	elif pathname == '/page-2':
		return html.Div([html.H3('Page 2 Content')])
	else:
		return html.Div([html.H3('Home Page Content')])

# Run the app
if __name__ == '__main__':
	app.run_server(debug=True)