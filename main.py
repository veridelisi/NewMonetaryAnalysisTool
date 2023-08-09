pip install evds --upgrade

import pandas as pd
import numpy as np

from evds import evdsAPI
evds = evdsAPI('k2QX6fe8eZ')
df=evds.get_data(['TP.AB.A02','TP.AB.A03', 'TP.AB.A08','TP.AB.A10','TP.AB.A17','TP.AB.A18','TP.AB.A21','TP.AB.A24','TP.AB.A25','TP.AB.A22'], startdate="01-01-2019", enddate="25-07-2023")

# Rename columns
new_column_names = ['Date','Foreign Assets', 'Domestic Assets', 'Revaluation', 'Total Foreign Liabilities', 'Currency Issued', 'Banking Reserves', 'Free Deposits', 'OMO', 'Deposits of Public Sector', 'Deposits of Non-Bank Sector']
df.columns = new_column_names

# Date column is the index
df.set_index('Date', inplace=True)

# Drop the NAN rows
df=df.dropna()
df

# Calculate the difference between two series and add a new column
df['Net Foreign Assets'] = df['Foreign Assets'] - df['Total Foreign Liabilities']
df

# Drop the original two series
df.drop(['Foreign Assets', 'Total Foreign Liabilities'], axis=1, inplace=True)
df

# Move the last column to the first position
last_column = df.pop('Net Foreign Assets')
df.insert(0, 'Net Foreign Assets', last_column)
df

# Delete the first row
df = df.iloc[1:]
df

# Calculate the first difference for all columns
df_diff = df.diff()
# Delete the first row
df_diff  = df_diff .iloc[1:]
df_diff

# Calculate the liquidity and add a new column
df_diff['Liquidity'] = df_diff['Net Foreign Assets']+ df_diff['Domestic Assets']+ df_diff['Revaluation']- df_diff['Currency Issued']- df_diff['Free Deposits'] - df_diff['Deposits of Public Sector'] - df_diff['Deposits of Non-Bank Sector'] 
df_diff

# OMO account is normally asset account but CBRT puts it liabilities side. We need to multiply with -1
df_diff['OMO']=df_diff['OMO'] * (-1)
df_diff

# The sum of the Liquidity and OMO need to be equal a Banking Reserves
# We create new series fro comparing with Banking Reserves
df_diff['Banking Reserves 2']=df_diff['OMO'] + df_diff['Liquidity']
df_diff



