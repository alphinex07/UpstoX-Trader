# StockTrader - Automated Stock Trading Web Application

StockTrader is a modern web application for automating stock trading using Excel input files. The application allows you to upload Excel files containing stock trading parameters, automatically executes buy/sell orders, implements stop loss functionality, and handles instrument token mapping.

## Features

- Upload and process Excel files containing stock trading parameters
- Automated buy/sell order execution based on Excel inputs
- Stop loss functionality with configurable thresholds from Excel
- Automatic mapping of stock symbols to instrument tokens
- Real-time trading status monitoring
- Order history tracking
- Responsive, modern UI with dark/light mode
- Secure authentication system for API token management

## Setup Instructions

1. Clone the repository
2. Install the required dependencies:

```bash
pip install -r requirements.txt
```

3. Set up the instrument mapping file:
   - Create a JSON file named `NSE.json` in the root directory
   - The file should contain an array of objects with at least `symbol` and `instrument_token` fields

4. Run the application:

```bash
python app.py
```

5. Access the web interface at `http://localhost:5000`

## Excel File Format

Your Excel file should have the following columns:

| Column | Description | Required | Example |
|--------|-------------|----------|---------|
| symbol | Stock symbol (NSE) | Yes (if no instrument_token) | RELIANCE |
| instrument_token | Upstox instrument token | Yes (if no symbol) | 2885634 |
| transaction_type | BUY or SELL | Yes | BUY |
| quantity | Number of shares | Yes | 5 |
| price | Order price (0 for market orders) | Yes | 2540.50 |
| order_type | MARKET or LIMIT | No (default: MARKET) | LIMIT |
| product | Product type (I: Intraday, D: Delivery) | No (default: I) | I |
| stop_loss_price | Price to trigger stop loss | No | 2500.00 |
| validity | Order validity (DAY, IOC) | No (default: DAY) | DAY |

## Stop Loss Feature

The stop loss feature monitors market prices for all buy orders with a specified stop loss price. When the current market price falls below the stop loss threshold, the system automatically places a sell order to limit losses.

## Instrument Token Mapping

The application can automatically map stock symbols to instrument tokens using the `NSE.json` file. If you provide only the symbol in your Excel file, the application will look up the corresponding instrument token.

## License

This project is licensed under the MIT License.