from collections import namedtuple
from datetime import datetime, timedelta
from pprint import pprint

from web3 import Web3
import json, math, os, sys, time, smtplib, ssl

import functions

RONIN_ADDRESS_PREFIX = "ronin:"

Transaction = namedtuple("Transaction", "from_address to_address amount")
Payout = namedtuple("Payout",
                    "name private_key nonce slp_balance account_address  scholar_transaction academy_transaction procentage ")
SlpClaim = namedtuple("SlpClaim", "name address private_key slp_claimed_balance slp_unclaimed_balance state")


def myexcepthook(type, value, traceback, oldhook=sys.excepthook):
    oldhook(type, value, traceback)
    input("Press RETURN. ")


sys.excepthook = myexcepthook


def parse_ronin_address(address):
    assert (address.startswith(RONIN_ADDRESS_PREFIX))
    return Web3.toChecksumAddress(address.replace(RONIN_ADDRESS_PREFIX, "0x"))


def adress_eth(address):
    return address.replace(RONIN_ADDRESS_PREFIX, "0x")


def format_ronin_address(address):
    return address.replace("0x", RONIN_ADDRESS_PREFIX)


def log(message="", end="\n"):
    print(message, end=end, flush=True)
    sys.stdout = log_file
    print(message, end=end)
    sys.stdout = original_stdout
    log_file.flush()


def wait(seconds):
    for i in range(0, seconds):
        time.sleep(1)
        log(".", end="")
    log()


# web3 = Web3(Web3.HTTPProvider('https://proxy.roninchain.com/free-gas-rpc'))

today = datetime.now()
log_path = f"logs/logs-{today.year}-{today.month:02}-{today.day:02}.txt"

if not os.path.exists(os.path.dirname(log_path)):
    os.makedirs(os.path.dirname(log_path))
log_file = open(log_path, "a", encoding="utf-8")
original_stdout = sys.stdout

log(f"# Program do wypłat SLP z szkółek # ({today})")

# if (len(sys.argv) != 2):
#     log("Proszę określić scieżkę do pliku config.")
#     exit()

nonces = {}

with open("konfiguracja_konta.json") as f:
    accounts = json.load(f)

academy_payout_address = parse_ronin_address(accounts["AcademyPayoutAddress"])

log("Sprawdzanie SLP do claimu", end="")
slp_claims = []
new_line_needed = False
for scholar in accounts["Scholars"]:
    scholarName = scholar["Name"]
    account_address = parse_ronin_address(scholar["AccountAddress"])

    slp_unclaimed_balance, days = functions.get_unclaimed_slp(account_address)

    nonce = nonces[account_address] = functions.web3_2.eth.get_transaction_count(account_address)

    if (slp_unclaimed_balance > 0):

        slp_per_day = slp_unclaimed_balance / days
        scholar["LastClaim"] = days

        # liczba_axie = functions.get_axie_number(adress_eth(scholar["AccountAddress"]))

        if slp_per_day > 60:
            procentage = 0.5
        elif 60 > slp_per_day >= 50:
            procentage = 0.5
        elif 50 > slp_per_day >= 35:
            procentage = 0.5
        elif slp_per_day < 34:
            procentage = 0.5
        # else:
        #     if slp_per_day > 120:
        #         procentage = 0.5
        #     elif 120 > slp_per_day >= 100:
        #         procentage = 0.5
        #     elif 100 > slp_per_day >= 70:
        #         procentage = 0.5
        #     elif slp_per_day < 69:
        #         procentage = 0.5

        scholar["ScholarPayoutPercentage"] = procentage

        if (new_line_needed):
            new_line_needed = False
            log()
        log(f"Konto '{scholarName}' (nonce: {nonce}) ma {slp_unclaimed_balance} niezclaimowane SLP.")

        slp_claims.append(SlpClaim(
            name=scholarName,
            address=account_address,
            private_key=scholar["PrivateKey"],
            slp_claimed_balance=functions.get_claimed_slp(account_address),
            slp_unclaimed_balance=slp_unclaimed_balance,
            state={"signature": None}))
    else:
        log(f".", end="")
        new_line_needed = True

with open("konfiguracja_konta.json", "w") as f:
    json.dump(accounts, f, indent=4)

if (new_line_needed):
    new_line_needed = False
    log()

if (len(slp_claims) > 0):
    log("Chcesz zclaimowac SLP? y/n", end=" ")

while (len(slp_claims) > 0):
    if (input() == "y"):
        for slp_claim in slp_claims:
            log(f"Claimowanie {slp_claim.slp_unclaimed_balance} SLP dla '{slp_claim.name}'...", end="")
            try:
                functions.execute_slp_claim(slp_claim, nonces)
            except Exception as e:
                log(f"   Błąd functions.execute_slp_claim: " + str(e))
                continue
            time.sleep(1)
            log("DONE")
        log("Oczekiwane, 30 sekund", end="")
        wait(30)

        completed_claims = []
        for slp_claim in slp_claims:
            if (slp_claim.state["signature"] != None):
                try:
                    slp_total_balance = functions.get_claimed_slp(slp_claim.address)
                except Exception as e:
                    log(f"   Błąd functions.get_claimed_slp: " + str(e))
                    continue

                if (slp_total_balance >= slp_claim.slp_claimed_balance + slp_claim.slp_unclaimed_balance):
                    completed_claims.append(slp_claim)

        for completed_claim in completed_claims:
            slp_claims.remove(completed_claim)
            nonces[completed_claim.address] += 1

        if (len(slp_claims) > 0):
            log("Ponizsze claimy nie przebiegły pomyślnie:")
            for slp_claim in slp_claims:
                log(f"  - Konto '{slp_claim.name}' ma {slp_claim.slp_unclaimed_balance} niezclaimowane SLP.")
            log(f"Powtórzyć claimy?")
        else:
            log("Wszystkie claimy przebiegły pomyślnie!")
    else:
        break

log()
log("Przejrzyj wypłaty dla poszczególnych szkółek:")

payouts = []

for scholar in accounts["Scholars"]:
    scholarName = scholar["Name"]
    account_address = parse_ronin_address(scholar["AccountAddress"])
    scholar_payout_address = parse_ronin_address(scholar["ScholarPayoutAddress"])

    slp_balance = functions.get_claimed_slp(account_address)

    if (slp_balance == 0):
        log(f"Omijam konto '{scholarName}' ({format_ronin_address(account_address)}) ponieważ ilość SLP równa się 0.")
        continue

    days = scholar["LastClaim"]
    try:
        slp_per_day = slp_balance / days
    except:
        print(scholarName + " Posiada SLP przed claimem!")
        input("Enter, zamknij")
        sys.exit()
        # liczba_axie = functions.get_axie_number(adress_eth(scholar["AccountAddress"]))

    if slp_per_day > 60:
        procentage = 0.5
    elif 60 > slp_per_day >= 50:
        procentage = 0.5
    elif 50 > slp_per_day >= 35:
        procentage = 0.5
    elif slp_per_day < 34:
        procentage = 0.5
    # else:
    #     if slp_per_day > 120:
    #         procentage = 0.5
    #     elif 120 > slp_per_day >= 100:
    #         procentage = 0.5
    #     elif 100 > slp_per_day >= 70:
    #         procentage = 0.5
    #     elif slp_per_day < 69:
    #         procentage = 0.5

    scholar["ScholarPayoutPercentage"] = procentage
    scholar_payout_percentage = scholar["ScholarPayoutPercentage"]

    assert (scholar_payout_percentage >= 0 and scholar_payout_percentage <= 1)

    scholar_payout_amount = math.ceil(slp_balance * scholar_payout_percentage)
    academy_payout_amount = slp_balance - scholar_payout_amount

    assert (scholar_payout_amount >= 0)
    assert (academy_payout_amount >= 0)
    assert (slp_balance == scholar_payout_amount + academy_payout_amount)

    payouts.append(Payout(
        name=scholarName,
        private_key=scholar["PrivateKey"],
        slp_balance=slp_balance,
        account_address=account_address,
        nonce=nonces[account_address],
        scholar_transaction=Transaction(from_address=account_address, to_address=scholar_payout_address,
                                        amount=scholar_payout_amount),
        academy_transaction=Transaction(from_address=account_address, to_address=academy_payout_address,
                                        amount=academy_payout_amount),
        procentage=scholar["ScholarPayoutPercentage"],

    )
    )

log()

if (len(payouts) == 0):
    exit()

for payout in payouts:
    log(f"Wypłata dla '{payout.name}'")
    log(f"├─ Stan SLP: {payout.slp_balance} SLP")
    log(f"├─ Nonce: {payout.nonce}")
    log(
        f"├─ Wypłata szkólki ({int((payout.procentage) * 100)}%): wyślę  {payout.scholar_transaction.amount:5} SLP z {format_ronin_address(payout.scholar_transaction.from_address)} do {format_ronin_address(payout.scholar_transaction.to_address)}")
    log(
        f"└─ Wypłata menaggera ({int((1 - payout.procentage) * 100)}%): wyśle {payout.academy_transaction.amount:5} SLP z {format_ronin_address(payout.academy_transaction.from_address)} do {format_ronin_address(payout.academy_transaction.to_address)}")
    log()

log("Chcesz wykonac transakcje ? (y/n) ?", end=" ")
while (len(payouts) > 0):
    if (input() != "y"):
        log("Żadne transakcje nie zostaną wykonane. Program się zatrzymuje.")
        exit()

    log()
    log("Wykonywanie transakcji...")
    for payout in payouts:
        log(f"Wypłata dla '{payout.name}'")
        if (nonces[payout.account_address] == payout.nonce):
            log(
                f"├─ Wypłata szkólki ({int((payout.procentage) * 100)}%): wysyłam  {payout.scholar_transaction.amount} SLP z {format_ronin_address(payout.scholar_transaction.from_address)} do {format_ronin_address(payout.scholar_transaction.to_address)}...",
                end="")
            try:
                hash = functions.transfer_slp(payout.scholar_transaction, payout.private_key, payout.nonce)
                # transaction_succes = functions.wait_confirmation(hash)
                log("Ukończono")
                log(f"│  Hash: {hash} - Explorer: https://explorer.roninchain.com/tx/{str(hash)}")
            except Exception as e:
                log(f"Ostrzezenie: " + str(e))
            time.sleep(0.350)
        else:
            log(f"├─ Wyplata dla szkolki zostala juz wyplacona.")

        if (nonces[payout.account_address] <= payout.nonce + 1):
            log(f"├─ Wypłata menaggera ({int((1 - payout.procentage) * 100)}%): wysyłam {payout.academy_transaction.amount} SLP z {format_ronin_address(payout.academy_transaction.from_address)} do {format_ronin_address(payout.academy_transaction.to_address)}...",
                end="")
            try:
                hash = functions.transfer_slp(payout.academy_transaction, payout.private_key, payout.nonce + 1)
                # transaction_succes = functions.wait_confirmation(hash)
                log("Ukończono")
                log(f"└─   Hash: {hash} - Explorer: https://explorer.roninchain.com/tx/{str(hash)}")
            except Exception as e:
                log(f"Ostrzezenie: " + str(e))
            time.sleep(0.350)
        else:
            log(f"└─ Wyplata dla menadzera zostala juz wyplacona.")
            assert (
                False)  # We should never get here because it means the full payout has succeeded and no need for a retry.
        log()
    log("Sprawdzanie transkacji ktore sie nie powiodly...")
    log("Czekanie 5 minut na nowe bloki...", end="")
    wait(60 * 5)

    completed_payouts = []
    for payout in payouts:
        expected_nonce = payout.nonce + 2
        actual_nonce = nonces[payout.account_address] = functions.web3_2.eth.get_transaction_count(
            payout.account_address)

        if (actual_nonce == expected_nonce):
            completed_payouts.append(payout)
        else:
            completed_steps = 2 - (expected_nonce - actual_nonce)
            log(
                f"Wyplata dla '{payout.name}' nie zostala ukonczona. Tylko {completed_steps} z 2. Spodziewany nonce: {expected_nonce}. Aktualny nonce: {actual_nonce}")

    for completed_payout in completed_payouts:
        payouts.remove(completed_payout)

    if (len(payouts) != 0):
        log("Czy chcesz powtorzyc proces wyplat?? ", end="")
    else:
        log("Wszystkie wyplaty przebiegly pomyslnie!")
        input("Nacisnij ENTER aby zakonczyc")
