pip install evds --upgrade
pip install  plotnine

# Import pandas and numpy
import pandas as pd
import numpy as np

# Import evds
from evds import evdsAPI

# Please put your  CBRT API key {https://evds2.tcmb.gov.tr-Profile Page-API Key}
evds = evdsAPI('..........')

# We download datas in the range 2013-2023
# https://evds2.tcmb.gov.tr/index.php?/evds/DataGroupLink/2/bie_abanlbil/en
# Central Bank Analytical Balance Sheet (Thousand TRY)(Business)
# Foreign Assets | TP.AB.A02                  Domestic Assets | TP.AB.A03               FX Revaluation Account | TP.AB.A08
# Total Foreign Liabilities | TP.AB.A10       Currency Issued | TP.AB.A17  
# Extra Budgetary Funds | TP.AB.A21           Deposits of Non-Bank Sector | TP.AB.A22   Deposits of Public Sector | TP.AB.A25
# Deposits of Banking Sector  | TP.AB.A18     Open Market Operations | TP.AB.A24

df=evds.get_data(['TP.AB.A02','TP.AB.A03', 'TP.AB.A08','TP.AB.A10','TP.AB.A17','TP.AB.A18','TP.AB.A21','TP.AB.A24','TP.AB.A25','TP.AB.A22'], startdate="12-08-2023", enddate="24-08-2023")

# Rename columns
new_column_names = ['Date','Foreign Assets', 'Domestic Assets', 'Revaluation', 'Total Foreign Liabilities', 'Currency Issued', 'Banking Reserves', 'Extra Funds', 'OMO', 'Deposits of Public Sector', 'Deposits of Non-Bank Sector']
df.columns = new_column_names

# We choose Date column as the index column
df.set_index('Date', inplace=True)

# Drop the NAN rows
df=df.dropna()
df

# Calculate the difference between Foreign Assets and Total Foreign Liabilities. This is Net Foreign Assets.
df['Net Foreign Assets'] = df['Foreign Assets'] - df['Total Foreign Liabilities']
df

# Drop the Foreign Assets and Total Foreign Liabilities columns
df.drop(['Foreign Assets', 'Total Foreign Liabilities'], axis=1, inplace=True)
df

# Move the last column to the first position
last_column = df.pop('Net Foreign Assets')
df.insert(0, 'Net Foreign Assets', last_column)
df

# Calculate the first difference for all columns
df_diff = df.diff()

# Delete the first row 
df_diff  = df_diff .iloc[1:]
df_diff

# Calculate the liquidity Situation
df_diff['Liquidity'] = df_diff['Net Foreign Assets']+ df_diff['Domestic Assets']+ df_diff['Revaluation']- df_diff['Currency Issued']- df_diff['Extra Funds'] - df_diff['Deposits of Public Sector'] - df_diff['Deposits of Non-Bank Sector'] 
df_diff

# OMO account is normally asset account but CBRT puts it liabilities side. We need to multiply with -1
df_diff['OMO']=df_diff['OMO'] * (-1)
df_diff

# The sum of the Liquidity and OMO need to be equal a Banking Reserves
# We create new series for comparing with Banking Reserves
# Please control whether Banking Reserves is rougly equal to  Banking Reserves 2
#df_diff['Banking Reserves 2']=df_diff['OMO'] + df_diff['Liquidity']
#df_diff

# Import the required libraries
from plotnine import ggplot, aes, geom_col, theme_minimal, labs, scale_y_continuous, theme, element_text


# Create a new DataFrame to hold the necessary columns for plotting
plot_df = df_diff[['OMO', 'Liquidity']].reset_index()

# Convert values to millions for better readability
plot_df['OMO'] /= 1e6
plot_df['Liquidity'] /= 1e6

# Melt the DataFrame to create a format suitable for stacked column plotting
plot_df = pd.melt(plot_df, id_vars=['Date'], value_vars=['OMO', 'Liquidity'])

# Create the stacked column plot using plotnine
p = (
    ggplot(plot_df, aes(x='Date', y='value', fill='variable')) +
    geom_col(position='stack') +
    labs(title='OMO and Liquidity', x='Date', y='Value (in millions)') +
    theme_minimal() +
    theme(figure_size=(10, 6))  # Adjust figure size
)

# Display the plot
print(p)


# Import the required libraries
from plotnine import ggplot, aes, geom_col, theme_minimal, labs, scale_y_continuous, theme, element_text



# Calculate the liquidity components for the same period
liquidity_components = df_diff[['Net Foreign Assets', 'Domestic Assets', 'Revaluation',
                                 'Currency Issued', 'Extra Funds',
                                 'Deposits of Public Sector', 'Deposits of Non-Bank Sector']].reset_index()

# Convert values to millions for better readability
liquidity_components = liquidity_components.apply(lambda col: col / 1e6 if col.name != 'Date' else col, axis=0)

# Melt the DataFrame to create a format suitable for stacked column plotting
liquidity_components = pd.melt(liquidity_components, id_vars=['Date'],
                               value_vars=['Net Foreign Assets', 'Domestic Assets', 'Revaluation',
                                           'Currency Issued', 'Extra Funds',
                                           'Deposits of Public Sector', 'Deposits of Non-Bank Sector'])

# Create a stacked column plot for liquidity components using plotnine
p_liquidity_components = (
    ggplot(liquidity_components, aes(x='Date', y='value', fill='variable')) +
    geom_col(position='stack') +
    labs(title='Liquidity Components', x='Date', y='Value (in millions)') +
    
    theme_minimal() +
    theme(figure_size=(10, 6))
)

# Display the plot for liquidity components
print(p_liquidity_components)

