from web3 import Web3
from eth_account import Account
from datetime import datetime
from dotenv import load_dotenv
import os
load_dotenv()

http = os.getenv("ETH_HTTP_PROVIDER","http://127.0.0.1:6102")




def deploy_contract(abi, bin, http_provider, account, private_key):
    w3 = Web3(Web3.HTTPProvider(http_provider))
    Contract = w3.eth.contract(abi=abi, bytecode=bin)

    transaction = Contract.constructor().build_transaction({
        'from': account,
        'nonce': w3.eth.get_transaction_count(account),
        'gas': 2000000,
        'gasPrice': w3.to_wei('1.1', 'gwei')
    })

    signed_txn = w3.eth.account.sign_transaction(transaction, private_key)
    tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    return tx_receipt



class address_storage_contract:
    def __init__(self, abi, contract_address, http_provider = http):
        self.base = Web3(Web3.HTTPProvider(http_provider))
        self.w3 = self.base.eth
        self.w3_functions = self.w3.contract(address=contract_address, abi=abi).functions

    def is_connected(self):
        return {'status': self.base.is_connected(), 'chain_id': self.w3.chain_id}

    def is_address(self, address):
        return Web3.is_address(address)

    def verify_key_pair(self, address, private_key):
        try:
            balance = self.w3.get_balance(address)
            if balance is None:
                return False
            acct = Account.from_key(private_key)
            return acct.address.lower() == address.lower()
        except Exception as e:
            print(f"Error verifying key pair: {e}")
            return False

    def get_balance(self, address):
        try:
            balance = self.w3.get_balance(address)
            return balance
        except Exception as e:
            print(f"Error Get Balance: {e}")
            return False

    def store_data(self, title : str,
                   metadata : str,
                   cid : str,
                   address : str,
                   private_key : str,
                   gas : int = 2000000):
        if not address or not private_key:
            raise ValueError("Public key and private key must be set before storing data.")
        try :
            nonce = self.w3.get_transaction_count(address)
            transaction = self.w3_functions.storeData(title, metadata, cid).build_transaction({
                'from': address,
                'gas': gas,
                'gasPrice': self.base.to_wei('1.1', 'gwei'),
                'nonce': nonce
            })

            signed_txn = self.w3.account.sign_transaction(transaction, private_key=private_key)
            tx_hash = self.w3.send_raw_transaction(signed_txn.raw_transaction)
            tx_receipt = self.w3.wait_for_transaction_receipt(tx_hash)
            return tx_receipt
        except Exception as e:
            print(f"An error occurred while storing data: {e}")
            return None

    def share_cid(self, receiver : str,
                   cid : str,
                   message : str,
                   address : str,
                   private_key : str,
                   gas : int = 2000000):
        if not address or not private_key:
            print("Public key and private key must be set before sharing data.")
            return None
        try :
            nonce = self.w3.get_transaction_count(address)
            transaction = self.w3_functions.transferCID(receiver, cid, message).build_transaction({
                'from': address,
                'gas': gas,
                'gasPrice': self.base.to_wei('1.1', 'gwei'),
                'nonce': nonce
            })

            signed_txn = self.w3.account.sign_transaction(transaction, private_key=private_key)
            tx_hash = self.w3.send_raw_transaction(signed_txn.raw_transaction)
            tx_receipt = self.w3.wait_for_transaction_receipt(tx_hash)
            return tx_receipt
        except Exception as e:
            print(f"An error occurred while storing data: {e}")
            return None

    def retrieve_latest_data(self, caller_address):
        count = self.w3_functions.getDataCount().call({'from':caller_address}) - 1
        return self.w3_functions.retrieveData(count).call({'from':caller_address})

    def get_count(self, caller_address):
        count = self.w3_functions.getDataCount().call({'from':caller_address})
        return count

    def get_account_receiver(self, caller_address):
        accounts = self.w3_functions.getReceivers().call({'from':caller_address})
        return accounts

    def get_share_count(self, caller_address, receiver_address, invert = False):
        if invert == False:
            return self.w3_functions.getShareCount(caller_address, receiver_address).call({'from':caller_address})
        else:
            return self.w3_functions.getShareCount(receiver_address, caller_address).call({'from':caller_address})



    def retrieve_all_data(self, caller_address):
        data = {'dt': [], 'title': [], 'metadata': [], 'cid': []}
        count = self.get_count(caller_address)
        for i in range(count):
            timestamp, title, metadata, cid = self.w3_functions.retrieveData(count-i-1).call({'from':caller_address})
            dt = datetime.fromtimestamp(timestamp)
            data['dt'].append(dt)
            data['title'].append(title)
            data['metadata'].append(metadata)
            data['cid'].append(cid)

        return data

    def get_all_history(self, caller_address, receiver_address):
        data = {'dt': [], 'cid': [], 'message': [], 'receiver': []}
        print(f"sender: {caller_address}, receiver: {receiver_address}")

        count = self.get_share_count(caller_address, receiver_address)
        print(f"non inverted count: {count}")

        if count != None or count > 0:
            for i in range(count):
                timestamp, cid, message = self.w3_functions.getShareHistory(caller_address, receiver_address, count-i-1).call({'from':caller_address})
                data['dt'].append(timestamp)
                data['cid'].append(cid)
                data['message'].append(message)
                data['receiver'].append('sent')
        print('first part done')
        count = self.get_share_count(caller_address, receiver_address, invert=True)
        print(f"inverted count: {count}")

        if count != None or count > 0:
            for i in range(count):
                timestamp, cid, message = self.w3_functions.getShareHistory(receiver_address, caller_address, count-i-1).call({'from':caller_address})
                data['dt'].append(timestamp)
                data['cid'].append(cid)
                data['message'].append(message)
                data['receiver'].append('received')
        print('second part done')
        # sort by datetime
        rows = list(zip(*data.values()))
        sort_index = list(data.keys()).index('dt')
        rows.sort(key=lambda x: x[sort_index], reverse=False)
        sorted_data = {key: list(col) for key, col in zip(data.keys(), zip(*rows))}
        print(sorted_data)
        return sorted_data