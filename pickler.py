import csv
import pickle

def save_tickers_from_csv():
  ticker_list = {}
  # open csv in read mode
  with open('StockWatch/tickers.csv', 'r') as csvfile:
    reader = csv.reader(csvfile)
    for row in reader:
      ticker = row[0]
      name = row[1]
      ticker_list[ticker] = name

  # open pickle file in write-binary mode
  with open('tickers.pickle ', 'wb') as f:
    pickle.dump(ticker_list, f)
  return ticker_list

if __name__ == "__main__":
  save_tickers_from_csv()




