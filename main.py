from fake_useragent import UserAgent
from web3 import Web3, HTTPProvider, Account
import requests
import json, random, time
import os
import colorlog
import logging



with open("Json_data.JSON", 'r') as f:
    config = json.load(f)
with open('private_keys.txt', 'r') as keys_file:
    private_keys = keys_file.read().splitlines()




desired_gas_price = int(input("Please enter your desired gas price: "))
min_delay = int(input("Please enter your minimum delay: "))
max_delay = int(input("Please enter your maximum delay: "))
Invite_per_linc = int(input("How mach refs per account you want?: "))


class ReferralSystem:
    def __init__(self, filename, usage_file='link_usage.json'):
        self.filename = filename
        self.usage_file = usage_file
        with open(filename, 'r') as f:
            self.links = f.read().splitlines()
        if os.path.exists(usage_file):
            with open(usage_file, 'r') as f:
                self.link_usage = json.load(f)
        else:
            self.link_usage = {}

    def get_link(self):
        for link in self.links:
            if link not in self.link_usage:
                self.link_usage[link] = 0
            if self.link_usage[link] < Invite_per_linc:
                return link
        return None

    def increment_link_usage(self, link):
        if link in self.link_usage:
            self.link_usage[link] += 1
            self.save_link_usage()
            if self.link_usage[link] == Invite_per_linc:
                self.cleanup_links()

    def save_link_usage(self):
        with open(self.usage_file, 'w') as f:
            json.dump(self.link_usage, f)

    def cleanup_links(self):
        self.links = [link for link in self.links if self.link_usage.get(link, 0) < Invite_per_linc]
        with open(self.filename, 'w') as f:
            for link in self.links:
                f.write(link + '\n')

def setup_logger(logger_name):
    logger = colorlog.getLogger(logger_name)

    # Removes previous handlers, if they exist.
    while logger.hasHandlers():
        logger.removeHandler(logger.handlers[0])

    handler = colorlog.StreamHandler()
    handler.setFormatter(
        colorlog.ColoredFormatter(
            "|%(log_color)s%(asctime)s| - Profile [%(name)s] - %(levelname)s - %(message)s",
            datefmt=None,
            reset=True,
            log_colors={
                'DEBUG':    'cyan',
                'INFO':     'green',
                'WARNING':  'yellow',
                'ERROR':    'red',
                'CRITICAL': 'red,bg_white',
            },
            secondary_log_colors={},
            style='%'
        )
    )
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return logger
def wait_for_gas_price_to_decrease(node_url, desired_gas_price):
    """
    This function checks the current base fee of Ethereum blockchain from a specific node
    and waits until it decreases to the desired level.

    :param node_url: URL of the Ethereum node.
    :param desired_gas_price: Desired base fee in Gwei.
    """
    while True:
        try:
            # Fetching the base fee for the latest block
            data = {
                "jsonrpc":"2.0",
                "method":"eth_getBlockByNumber",
                "params":['latest', True],
                "id":1
            }

            headers = {'Content-Type': 'application/json'}
            response = requests.post(node_url, headers=headers, data=json.dumps(data))
            response.raise_for_status()

            result = response.json()['result']
            current_base_fee = int(result['baseFeePerGas'], 16) / 10**9  # Convert from Wei to Gwei

        except requests.exceptions.HTTPError as errh:
            print(f"HTTP Error: {errh}")
            time.sleep(10)  # Retry after 10 sec in case of a HTTP error
            continue
        except requests.exceptions.ConnectionError as errc:
            print(f"Error Connecting: {errc}")
            time.sleep(10)  # Retry after 10 sec in case of a connection error
            continue

        if current_base_fee <= desired_gas_price:
            break  # Exit the loop if the base fee is less than or equal to the desired level
        else:
            print(
                f"Current base fee ({current_base_fee} Gwei) is higher than desired ({desired_gas_price} Gwei). Waiting...",
                end="", flush=True)
            time.sleep(10)  # Message displayed for 10 seconds
            print("\033[K", end="\r", flush=True)  # Check the base fee every 10 sec
def get_sign(main_address: str, referrer: str):
    while True:
        try:
            url = f'https://mint.fun/api/mintfun/fundrop/mint?address={main_address}&referrer={referrer}'

            headers ={
                'User-Agent':UserAgent().random,
                'Referer':f'https://mint.fun/fundrop?ref={referrer}',
            }

            resp = requests.get(url, headers=headers)
            if resp.status_code == 200:
                a = json.loads(resp.text)
                sign = a['signature']
                return sign
        except Exception:
            print("Shit go wrong")
def mint(config, private_key, nugger):

    w3 = Web3(HTTPProvider(config['networks']['Ethereum']['url']))
    account = w3.eth.account.from_key(private_key)
    address_checksum = address = w3.to_checksum_address(account.address)
    contract_name = "MintFun"
    contract_details = config['contracts'][contract_name]
    contract_address = w3.to_checksum_address(contract_details['address'])
    contract = w3.eth.contract(address=contract_address, abi=contract_details['abi'])

    base_fee = w3.eth.fee_history(w3.eth.get_block_number(), 'latest')['baseFeePerGas'][-1]
    priority_max = w3.to_wei(0.6, 'gwei')

    # Fetch a link but don't increment the counter yet
    ref_sys = ReferralSystem('ref_links.txt')
    link = ref_sys.get_link()
    if link is None:
        nugger.error("You have no link man, go find some more...")
        exit("System termination")

    referrer = str(link)
    referrer = w3.to_checksum_address(referrer)
    signature = get_sign(address, referrer)

    swap_txn = contract.functions.mint(referrer, signature).build_transaction({
        'from': address,
        'nonce': w3.eth.get_transaction_count(account.address),
        'maxFeePerGas': base_fee + priority_max,
        'maxPriorityFeePerGas': priority_max
    })

    # Estimate gas limit and update the transaction
    estimated_gas_limit = round(w3.eth.estimate_gas(swap_txn))
    swap_txn.update({'gas': estimated_gas_limit})

    # Sign transaction using private key
    signed_txn = w3.eth.account.sign_transaction(swap_txn, private_key)

    try:
        txn_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        txn_receipt = w3.eth.wait_for_transaction_receipt(txn_hash, timeout=666)
    except ValueError or Exception:
        nugger.warning("Insufficient funds for transaction.")
        nugger.warning("Or it may be any other shit, check manual")
        with open('failed_transactions.txt', 'a') as f:
            f.write(f'{address_checksum}, transaction failed due to error\n')
        return 0


        # Check the status field for success
    if txn_receipt['status'] == 1:
        # Increment the link usage here after success
        ref_sys.increment_link_usage(link)

        # Remove the private key from the list after a successful transaction
        if private_key in private_keys:
            private_keys.remove(private_key)

        # Optionally, you can save the modified list to the 'private_keys.txt' file if needed:
        with open('private_keys.txt', 'w') as keys_file:
            for key in private_keys:
                keys_file.write(key + '\n')

        nugger.info(f"Transaction was successful...")
        nugger.info(f"Txn hash: https://etherscan.io/tx/{txn_hash.hex()}")
        with open('successful_transactions.txt', 'a') as f:
            f.write(f'{address_checksum}, successful transaction, Txn hash: https://etherscan.io/tx/{txn_hash.hex()}\n')
        return 1
    elif txn_receipt['status'] == 0:
        nugger.warning("Transaction was unsuccessful.")
        nugger.warning(f"Txn hash: https://etherscan.io/tx/{txn_hash.hex()}")
        with open('failed_transactions.txt', 'a') as f:
            f.write(f'{address_checksum}, transaction failed, Txn hash: https://etherscan.io/tx/{txn_hash.hex()}\n')
        return 0

def main():
    print("Author channel: https://t.me/CryptoBub_ble")
    random.shuffle(private_keys)
    nugger = setup_logger("nugger")
    for id, private_key in enumerate(private_keys):
        account = Account.from_key(private_key)
        wait_for_gas_price_to_decrease("https://ethereum.publicnode.com", desired_gas_price)
        nugger.info(f"Started work with wallet: {account.address}")

        mint(config, private_key, nugger)

        slp = random.randint(min_delay, max_delay)
        nugger.warning(f"Sleep for {slp} second before next operation...")
        nugger.error("Subscribe - https://t.me/CryptoBub_ble")
        time.sleep(slp)


if __name__ == '__main__':
    main()

