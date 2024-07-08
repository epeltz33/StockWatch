
---

# 📈 StockWatch

## Overview

The **StockWatch App** is a web-based application designed to help users monitor and manage their stock portfolios. Built with **Flask** for the backend and **Plotly Dash** for the frontend, this app allows users to track their favorite stocks, view historical data, and maintain a personalized watchlist.

## Features

- 🔐 **User Authentication**: Secure registration and login functionalities.
- 📊 **Stock Data Integration**: Fetch delayed stock data using the Polygon.io API.
- 📈 **Watchlist Management**: Add, view, and remove stocks from your personalized watchlist.
- 📉 **Data Visualization**: Interactive charts and graphs to visualize stock performance.
- 📱 **Responsive Design**: Accessible on desktop.

## Technology Stack

- **Backend**: Flask, SQLAlchemy
- **Frontend**: Plotly Dash, Dash Bootstrap Components, CSS
- **Database**: SQLite
- **API**: Polygon.io
- **Development Tools**: PyCharm, DataGrip, GitHub, VScode
- **Deployment**: tbd

## Installation

### Prerequisites

- Python 3.12
- Pipenv
- tbd

### Steps

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/yourusername/stock-tracker-app.git
   cd stock-tracker-app
   ```

2. **Set Up Virtual Environment**:
   ```bash
   pipenv --python 3.12
   pipenv install
   ```

3. **Set Up Environment Variables**:
   Create a `.env` file in the root directory and add your configuration:
   ```plaintext
   SECRET_KEY=your_secret_key
   DATABASE_URL=mysql://username:password@localhost/dbname
   POLYGON_API_KEY=your_polygon_api_key
   ```

4. **Initialize the Database**:
   ```bash
   pipenv run flask db upgrade
   ```

5. **Run the Application**:
   ```bash
   pipenv run flask run
   ```
   

## Usage

1. **Register and Login**:
   - Navigate to the registration page to create an account.
   - Use your credentials to log in.

2. **Search for Stocks**:
   - Use the search functionality to find stocks and view their data.

3. **Add to Watchlist**:
   - Add stocks to your watchlist for easy tracking.

4. **View Data**:
   - Access historical data visualized through interactive charts.
     


## Contact

For questions or feedback, please contact [erpeltz@gmail.com](mailto:erpeltz@gmail.com).

---

