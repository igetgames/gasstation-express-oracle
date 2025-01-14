"""gasstation oracle"""
import time
import json
import traceback
import pandas as pd
import numpy as np
from web3 import Web3, HTTPProvider


web3 = Web3(HTTPProvider('http://localhost:8545')) # pylint: disable=invalid-name

# These are the threholds used for % blocks accepting to define the recommended gas prices. can be
# edited here if desired

SAFELOW = 35
STANDARD = 60
FAST = 90

class Timers(): # pylint: disable=too-few-public-methods
    """
    class to keep track of time relative to network block
    """
    def __init__(self, start_block):
        self.start_block = start_block
        self.current_block = start_block
        self.process_block = start_block

    def update_time(self, block):
        """update the current and processing blocks"""
        self.current_block = block
        self.process_block = self.process_block + 1

class CleanTx():
    """transaction object / methods for pandas"""
    def __init__(self, tx_obj):
        self.hash = tx_obj.hash
        self.block_mined = tx_obj.blockNumber
        self.gas_price = tx_obj['gasPrice']
        self.round_gp_10gwei()

    def to_dataframe(self):
        """convert transaction object to a Pandas DataFrame"""
        data = {
            self.hash: {
                'block_mined': self.block_mined,
                'gas_price': self.gas_price,
                'round_gp_10gwei': self.gp_10gwei
            }
        }
        return pd.DataFrame.from_dict(data, orient='index')

    def round_gp_10gwei(self):
        """Rounds the gas price to gwei"""
        gas_price = self.gas_price/1e8
        if 1 <= gas_price < 10:
            gas_price = np.floor(gas_price)
        elif gas_price >= 10:
            gas_price = gas_price/10
            gas_price = np.floor(gas_price)
            gas_price = gas_price*10
        else:
            gas_price = 0
        self.gp_10gwei = gas_price

class CleanBlock():
    """block object/methods for pandas"""
    def __init__(self, block_obj, timemined, mingasprice=None):
        self.block_number = block_obj.number
        self.time_mined = timemined
        self.blockhash = block_obj.hash
        self.mingasprice = mingasprice

    def to_dataframe(self):
        """convert block object to a Pandas DataFrame"""
        data = {
            0: {
                'block_number': self.block_number,
                'blockhash': self.blockhash,
                'time_mined': self.time_mined,
                'mingasprice': self.mingasprice
            }
        }
        return pd.DataFrame.from_dict(data, orient='index')

def write_to_json(gprecs, prediction_table):
    """write json data"""
    try:
        prediction_table['gasprice'] = prediction_table['gasprice']/10
        prediction_tableout = prediction_table.to_json(orient='records')
        filepath_gprecs = 'ethgasAPI.json'
        filepath_prediction_table = 'predictTable.json'

        with open(filepath_gprecs, 'w') as outfile:
            json.dump(gprecs, outfile)

        with open(filepath_prediction_table, 'w') as outfile:
            outfile.write(prediction_tableout)

    except IOError as error:
        print(error)

def process_block_transactions(block):
    """get tx data from block"""
    block_df = pd.DataFrame()
    block_obj = web3.eth.getBlock(block, True)
    for transaction in block_obj.transactions:
        clean_tx = CleanTx(transaction)
        block_df = block_df.append(clean_tx.to_dataframe(), ignore_index=False)
    block_df['time_mined'] = block_obj.timestamp
    return(block_df, block_obj)

def process_block_data(block_df, block_obj):
    """process block to dataframe"""
    if block_obj.transactions:
        block_mingasprice = block_df['round_gp_10gwei'].min()
    else:
        block_mingasprice = np.nan
    timemined = block_df['time_mined'].min()
    clean_block = CleanBlock(block_obj, timemined, block_mingasprice)
    return clean_block.to_dataframe()

def get_hpa(gasprice, hashpower):
    """gets the hash power accpeting the gas price over last 200 blocks"""
    hpa = hashpower.loc[gasprice >= hashpower.index, 'hashp_pct']
    if gasprice > hashpower.index.max():
        hpa = 100
    elif gasprice < hashpower.index.min():
        hpa = 0
    else:
        hpa = hpa.max()
    return int(hpa)

def analyze_last200blocks(block, blockdata):
    """analyze the previous 200 blocks"""
    recent_blocks = \
        blockdata.loc[blockdata['block_number'] > (block-200), ['mingasprice', 'block_number']]
    #create hashpower accepting dataframe based on mingasprice accepted in block
    hashpower = recent_blocks.groupby('mingasprice').count()
    hashpower = hashpower.rename(columns={'block_number': 'count'})
    hashpower['cum_blocks'] = hashpower['count'].cumsum()
    totalblocks = hashpower['count'].sum()
    hashpower['hashp_pct'] = hashpower['cum_blocks']/totalblocks*100
    #get avg blockinterval time
    blockinterval = recent_blocks.sort_values('block_number').diff()
    blockinterval.loc[blockinterval['block_number'] > 1, 'time_mined'] = np.nan
    blockinterval.loc[blockinterval['time_mined'] < 0, 'time_mined'] = np.nan
    avg_timemined = blockinterval['time_mined'].mean()
    if np.isnan(avg_timemined):
        avg_timemined = 15
    return(hashpower, avg_timemined)

def make_prediction_table(hashpower):
    """create a gas price prediction table"""

    #predictiontable
    prediction_table = pd.DataFrame({'gasprice' :  range(10, 1010, 10)})
    ptable2 = pd.DataFrame({'gasprice' : range(0, 10, 1)})
    prediction_table = prediction_table.append(ptable2).reset_index(drop=True)
    prediction_table = prediction_table.sort_values('gasprice').reset_index(drop=True)
    prediction_table['hashpower_accepting'] = \
        prediction_table['gasprice'].apply(get_hpa, args=(hashpower,))
    return prediction_table

def get_gasprice_recs(prediction_table, block_time, block):
    """return gas price records"""

    def get_safelow():
        series = prediction_table.loc[prediction_table['hashpower_accepting'] >=
                                      SAFELOW, 'gasprice']
        safelow = series.min()
        return float(safelow)

    def get_average():
        series = prediction_table.loc[prediction_table['hashpower_accepting'] >=
                                      STANDARD, 'gasprice']
        average = series.min()
        return float(average)

    def get_fast():
        series = prediction_table.loc[prediction_table['hashpower_accepting'] >= FAST, 'gasprice']
        fastest = series.min()
        return float(fastest)

    def get_fastest():
        hpmax = prediction_table['hashpower_accepting'].max()
        fastest = prediction_table.loc[prediction_table['hashpower_accepting'] ==
                                       hpmax, 'gasprice'].values[0]
        return float(fastest)

    gprecs = {}
    gprecs['safeLow'] = get_safelow()/10
    gprecs['standard'] = get_average()/10
    gprecs['fast'] = get_fast()/10
    gprecs['fastest'] = get_fastest()/10
    gprecs['block_time'] = block_time
    gprecs['blockNum'] = block
    return gprecs

def master_control():
    """orcacle entrypoint"""

    def init(block):
        nonlocal alltx
        nonlocal blockdata
        print("\n\n**** ETH Gas Station Express Oracle ****\n")
        # pylint: disable=line-too-long
        print("Safelow = %d%% of blocks accepting. Usually confirms in less than 30min." % (SAFELOW))
        print("Standard= %d%% of blocks accepting. Usually confirms in less than 5 min." % (STANDARD))
        print("Fast = %d%% of blocks accepting. Usually confirms in less than 1 minute" % (FAST))
        print("Fastest = all blocks accepting. As fast as possible but you are probably overpaying.")
        # pylint: enable=line-too-long
        print("\nnow loading gasprice data from last 100 blocks...give me a minute")

        for pastblock in range((block-100), (block), 1):
            (mined_blockdf, block_obj) = process_block_transactions(pastblock)
            alltx = alltx.combine_first(mined_blockdf)
            block_sumdf = process_block_data(mined_blockdf, block_obj)
            blockdata = blockdata.append(block_sumdf, ignore_index=True)
        print("done. now reporting gasprice recs in gwei: \n")

        print("\npress ctrl-c at any time to stop monitoring\n")
        print("**** And the oracle says...**** \n")

    def update_dataframes(block):
        nonlocal alltx
        nonlocal blockdata
        nonlocal timer

        try:
            #get minedtransactions and blockdata from previous block
            mined_block_num = block-3
            (mined_blockdf, block_obj) = process_block_transactions(mined_block_num)
            alltx = alltx.combine_first(mined_blockdf)

            #process block data
            block_sumdf = process_block_data(mined_blockdf, block_obj)

            #add block data to block dataframe
            blockdata = blockdata.append(block_sumdf, ignore_index=True)

            #get hashpower table from last 200 blocks
            (hashpower, block_time) = analyze_last200blocks(block, blockdata)
            predictiondf = make_prediction_table(hashpower)

            #get gpRecs
            gprecs = get_gasprice_recs(predictiondf, block_time, block)
            print(gprecs)

            #every block, write gprecs, predictions
            write_to_json(gprecs, predictiondf)

        except: # pylint: disable=bare-except
            print(traceback.format_exc())

    alltx = pd.DataFrame()
    blockdata = pd.DataFrame()
    timer = Timers(web3.eth.blockNumber)
    init(web3.eth.blockNumber)

    while True:
        try:
            block = web3.eth.blockNumber
            if timer.process_block < block:
                update_dataframes(timer.process_block)
                timer.process_block = timer.process_block + 1
        except: # pylint: disable=bare-except
            pass

        time.sleep(1)

master_control()
