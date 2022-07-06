from datetime import datetime, timedelta
from eth_account.messages import encode_defunct
from web3 import Web3, exceptions
import json, requests, time

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.77 Safari/537.36"
headers = {
    "Content-Type": "application/json",
    "User-Agent": USER_AGENT}

web3_2 = Web3(Web3.HTTPProvider('https://api.roninchain.com/rpc', request_kwargs={"headers": headers}))

with open('slp_abi.json') as f:
    slp_abi = json.load(f)
slp_contract = web3_2.eth.contract(address=Web3.toChecksumAddress("0xa8754b9fa15fc18bb59458815510e40a12cd2014"),
                                   abi=slp_abi)

headers = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.77 Safari/537.36"}


def get_claimed_slp(address):
    return int(slp_contract.functions.balanceOf(address).call())


def wait_confirmation(txn):
    """
    Wait for a transaction to finish
    :param txn: the transaction to wait
    :return: True or False depending if transaction succeed
    """
    for i in range(20):
        try:
            recepit = web3_2.eth.get_transaction_receipt(txn)
            success = True if recepit["status"] == 1 else False
            return success
        except exceptions.TransactionNotFound:
            time.sleep(5)
            if i == 19:
                return False


def get_unclaimed_slp(address):
    for i in range(50):
        response = requests.get(f"https://game-api-pre.skymavis.com/v1/players/{address}/items/1", headers=headers,
                                data="")
        if (response.status_code == 200): break
        time.sleep(1)
    if (response.status_code != 200):
        print(response.text)
    assert (response.status_code == 200)
    result = response.json()

    total = int(result["total"]) - int(result["claimableTotal"])

    last_claimed_item_at = datetime.utcfromtimestamp(int(result["lastClaimedItemAt"]))

    days = round((datetime.utcnow() - last_claimed_item_at).total_seconds() / 86400)
    if (datetime.utcnow() + timedelta(days=-14) < last_claimed_item_at):
        total = 0

    return total, days


def execute_slp_claim(claim, nonces):
    if (claim.state["signature"] == None):
        access_token = get_jwt_access_token(claim.address, claim.private_key)

        custom_headers = headers.copy()
        custom_headers["authorization"] = f"Bearer {access_token}"
        for i in range(5):
            response = requests.post(f"https://game-api-pre.skymavis.com/v1/players/me/items/1/claim",
                                     headers=custom_headers)
            if (response.status_code == 200): break
            time.sleep(1)
            if (response.status_code != 200):
                print(response.text)
        assert (response.status_code == 200)
        result = response.json()["blockchainRelated"]["signature"]
        claim.state["signature"] = result["signature"].replace("0x", "")
        claim.state["amount"] = result["amount"]
        claim.state["timestamp"] = result["timestamp"]

    nonce = nonces[claim.address]
    claim_txn = slp_contract.functions.checkpoint(claim.address, result["amount"], result["timestamp"],
                                                  claim.state["signature"]).buildTransaction(
        {'gas': 2000000, 'gasPrice': web3_2.toWei(1, 'gwei'), 'nonce': nonce})

    signed_txn = web3_2.eth.account.sign_transaction(claim_txn,
                                                     private_key=bytearray.fromhex(claim.private_key.replace("0x", "")))
    web3_2.eth.send_raw_transaction(signed_txn.rawTransaction)
    hash = web3_2.toHex(web3_2.keccak(signed_txn.rawTransaction))
    # wait_confirmation(hash)

    return web3_2.toHex(web3_2.keccak(signed_txn.rawTransaction))  # Returns transaction hash.


def transfer_slp(transaction, private_key, nonce):
    transfer_txn = slp_contract.functions.transfer(
        transaction.to_address,
        transaction.amount).buildTransaction({
        'chainId': 2020,
        'gas': 100000,
        'gasPrice': web3_2.toWei('1', 'gwei'),
        'nonce': nonce,
    })

    signed_txn = web3_2.eth.account.sign_transaction(transfer_txn,
                                                     private_key=bytearray.fromhex(private_key.replace("0x", "")))
    web3_2.eth.send_raw_transaction(signed_txn.rawTransaction)
    return web3_2.toHex(web3_2.keccak(signed_txn.rawTransaction))  # Returns transaction hash.


def sign_message(message, private_key):
    message_encoded = encode_defunct(text=message)
    message_signed = Web3().eth.account.sign_message(message_encoded, private_key=private_key)
    return message_signed['signature'].hex()


def get_jwt_access_token(address, private_key):
    random_message = create_random_message()
    random_message_signed = sign_message(random_message, private_key)

    payload = {
        "operationName": "CreateAccessTokenWithSignature",
        "variables": {
            "input": {
                "mainnet": "ronin",
                "owner": f"{address}",
                "message": f"{random_message}",
                "signature": f"{random_message_signed}"
            }
        },
        "query": "mutation CreateAccessTokenWithSignature($input: SignatureInput!) {    createAccessTokenWithSignature(input: $input) {      newAccount      result      accessToken      __typename    }  }  "
    }
    for i in range(5):
        response = requests.post("https://graphql-gateway.axieinfinity.com/graphql", headers=headers, json=payload)
        if (response.status_code == 200): break
        time.sleep(1)

    if (response.status_code != 200):
        print(response.text)
    assert (response.status_code == 200)
    return response.json()['data']['createAccessTokenWithSignature']['accessToken']


def create_random_message():
    payload = {
        "operationName": "CreateRandomMessage",
        "variables": {},
        "query": "mutation CreateRandomMessage {    createRandomMessage  }  "
    }
    for i in range(5):
        response = requests.post("https://graphql-gateway.axieinfinity.com/graphql", headers=headers, json=payload)
        if (response.status_code == 200): break
        time.sleep(1)
    if (response.status_code != 200):
        print(response.text)
    assert (response.status_code == 200)
    return response.json()["data"]["createRandomMessage"]


def get_axie_number(account_address):
    account_address = account_address.replace("ronin:", "0x")
    payload = {
        "operationName": "GetAxieBriefList",
        "query": "query GetAxieBriefList($auctionType: AuctionType, $criteria: AxieSearchCriteria, $from: Int, $sort: SortBy, $size: Int, $owner: String, $filterStuckAuctions: Boolean) {\n  axies(\n    auctionType: $auctionType\n    criteria: $criteria\n    from: $from\n    sort: $sort\n    size: $size\n    owner: $owner\n    filterStuckAuctions: $filterStuckAuctions\n  ) {\n    total\n    results {\n      ...AxieBrief\n      __typename\n    }\n    __typename\n  }\n}\n\nfragment AxieBrief on Axie {\n  id\n  name\n  stage\n  class\n  breedCount\n  image\n  title\n  battleInfo {\n    banned\n    __typename\n  }\n  auction {\n    currentPrice\n    currentPriceUSD\n    __typename\n  }\n  parts {\n    id\n    name\n    class\n    type\n    specialGenes\n    __typename\n  }\n  __typename\n}\n",
        "variables": {
            'auctionType': "All",
            'criteria': {
                'bodyShapes': None,
                'breedCount': None,
                'breedable': None,
                'classes': None,
                'hp': [],
                'morale': [],
                'numJapan': None,
                'numMystic': None,
                'numXmas': None,
                'parts': None,
                'pureness': None,
                'purity': [],
                'region': None,
                'skill': [],
                'speed': [],
                'stages': None,
                'title': None
            },
            'from': 0,
            'owner': account_address,
            'size': 24,
            'sort': "IdDesc"
        }
    }
    # payload = json.dumps(payload)
    for i in range(5):
        response = requests.post("https://graphql-gateway.axieinfinity.com/graphql", headers=headers, json=payload)
        if (response.status_code == 200): break
        time.sleep(1)
    if (response.status_code != 200):
        print(response.text)
    assert (response.status_code == 200)
    axie_number = str(response.json()["data"]["axies"]["total"])
    if axie_number.isdigit():
        return int(axie_number)
    else:
        return 0
