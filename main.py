"""
Author: Lexi Virta
Date: 2025-12-10
Description: Dynamic pizza creation option prompter
"""

import pyinputplus as pyip
from datetime import datetime
from pathlib import Path
import requests
import json
import os

ENDPOINT_URL = "https://itec-minneapolis.s3.us-west-2.amazonaws.com/ingredients.json"
INGREDIENTS_CACHE_FILE = Path.resolve(Path("./ingredients.cache.json"))
ORDERS_DIRECTORY = Path.resolve(Path("./orders/"))
CART_FILE = Path.resolve(Path("./cart.json"))
PRICED_ITEM_FORMAT = "{:<48} ${:>8.2f}"

"""
{
    ["category"]: {
        ["option"]: [price],
        ...
    }
}
"""
all_base_options = dict()

"""
{
    ["topping"]: [price],
    ...
}
"""
all_toppings = dict()

cart = list()

def download_ingredients():
    ingredients_json = None

    # ask the server first
    try:
        response = requests.get(ENDPOINT_URL)
        response.raise_for_status()

        ingredients_json = json.loads(response.text)

        # try to locally cache the ingredients in case of server outage
        try:
            # create directories out to the cache file location
            os.makedirs(os.path.dirname(INGREDIENTS_CACHE_FILE), exist_ok=True)
            with open(INGREDIENTS_CACHE_FILE, "w") as cache_file:
                cache_file.write(response.text)
        except Exception as error:
            print("Error saving ingredients cache file")
            print(error)
    
    except json.JSONDecodeError:
        # if the server is returning a valid response, but malformed data, then fail
        print("Malformed ingredient data received from endpoint")
        return False
    
    # if the server itself can't handle the request properly or is offline
    except requests.HTTPError:
        # try loading the ingredients from the cache
        cache_file_exists = False
        try:
            cache_file_exists = Path.exists(INGREDIENTS_CACHE_FILE)
        except Exception as error:
            print("Failed to check cache file existence")
            print(error)

        if cache_file_exists:
            try:
                # load the ingredients from the local cache
                with open(INGREDIENTS_CACHE_FILE, "r") as cache_file:
                    ingredients_json = json.loads(cache_file.read())
                    print("Server is offline; loading cached ingredients")
            except Exception as error:
                print("Error reading ingredients cache file")
                print(error)
                return False
        else:
            # if everything fails
            print("Unable to connect to endpoint, and cannot read ingredients cache")
            return False
    
    # check if the fields are properly formed
    try:
        assert type(ingredients_json["base_options"][0]["category"] + "") is str
        assert ingredients_json["base_options"][0]["options"].keys() is not None
        assert ingredients_json["toppings"].keys() is not None
    except Exception as error:
        print("Ingredient data is improperly formed")
        return False

    # finally load the data if it was able to be retrieved and is properly formed
    all_base_options.clear()
    for base_options in ingredients_json["base_options"]:
        all_base_options[base_options["category"]] = base_options["options"]

    all_toppings.clear()
    for topping, price in ingredients_json["toppings"].items():
        all_toppings[topping] = price
    
    return True

def main():
    print("Downloading latest menu...")
    download_succeeded = download_ingredients()
    if not download_succeeded:
        print("Menu download failed!")
        return
    
    if not load_cart(CART_FILE):
        print("A new cart file will be created when the order is modified")
    
    print("=== Welcome to Dynamic Pizza Creation Option Prompter ===")
    while True:
        total_prices = 0
        for pizza in cart:
            total_prices += calculate_pizza_price(pizza)

        choice = input_menu_indexed({
            "new": "New pizza",
            "edit": "Edit existing pizza",
            "remove": "Remove a pizza",
            "restart": "Start over",
            "checkout": PRICED_ITEM_FORMAT.format("Checkout", total_prices)
        }, numbered=True)

        if choice == "new":
            command_new()
            save_cart(CART_FILE)
        elif choice == "edit":
            command_edit()
            save_cart(CART_FILE)
        elif choice == "remove":
            command_remove()
            save_cart(CART_FILE)
        elif choice == "restart":
            if pyip.inputYesNo(f"Delete {len(cart)} cart item(s)? (y/n) ") == "yes":
                if clear_cart(CART_FILE):
                    print("Cleared the cart successfully")
        elif choice == "checkout":
            if command_checkout():
                print("")
                if create_order():
                    print("Thank you for using the program!")
                    clear_cart(CART_FILE)
                    return

def save_cart(cart_filepath):
    # convert cart to json string
    cart_file_data = json.dumps(cart)

    # try saving the file
    try:
        # create directories out to the cart file location
        os.makedirs(os.path.dirname(cart_filepath), exist_ok=True)

        with open(cart_filepath, "w") as cart_file:
            cart_file.write(cart_file_data)
    except Exception as error:
        print("Failed to save cart")
        print(error)

def load_cart(cart_filepath):    
    # try reading the cart first
    cart_file_data = ""
    try:
        # make sure the cart exists before trying to load it
        if not Path.exists(cart_filepath):
            return False
        
        with open(cart_filepath, "r") as cart_file:
            cart_file_data = cart_file.read()
    except Exception as error:
        print("Failed to read cart")
        print(error)
    
    # then try loading the cart
    loaded_cart = None
    try:
        loaded_cart = json.loads(cart_file_data)
    except json.JSONDecodeError:
        print("Malformed cart data")
        return False

    cart.clear()
    for pizza in loaded_cart:
        cart.append(pizza)
    
    return True

def clear_cart(cart_filepath):
    try:
        if Path.exists(cart_filepath):
            Path.unlink(cart_filepath)
    except Exception as error:
        print("Failed to clear cart")
        print(error)
        return False

    return True


def input_menu_indexed(choices, **kwargs):
    # prompt the values of the choices dict
    choice_response = pyip.inputMenu(list(choices.values()), **kwargs)

    # find the index of the choice, then find the original key in the choices dict
    choice_values = list(choices.values())
    if choice_response not in choice_values: return None
    return list(choices.keys())[choice_values.index(choice_response)]

def choose_toppings(pizza_toppings, available_toppings):
    while True:
        choices = {}

        # add topping choices (checkmark if selected)
        for topping in available_toppings:
            prefix = topping in pizza_toppings and "[✓] " or "[ ] "
            choices[topping] = PRICED_ITEM_FORMAT.format(prefix + topping.title(), all_toppings[topping])

        choices["$exit"] = "Save"

        choice = input_menu_indexed(choices, numbered=True)

        if choice == "$exit":
            return
        else:
            if choice in pizza_toppings:
                pizza_toppings.remove(choice)
            else:
                pizza_toppings.append(choice)

def choose_base_option(category, base_options, pizza_options):
    choices = {}

    for option_name in base_options.keys():
        prefix = option_name == pizza_options[category] and "[✓] " or "[ ] "
        choices[option_name] = PRICED_ITEM_FORMAT.format(prefix + option_name.title(), all_base_options[category][option_name])
    
    choice = input_menu_indexed(choices, prompt=f"Select an option for {category.title()}:\n", numbered=True, blank=True)
    print(choice)
    
    pizza_options[category] = choice or pizza_options[category]

def edit_pizza(pizza):
    while True:
        choices = {}
        all_required_picked = True

        for category in all_base_options.keys():
            selection = pizza["base_options"][category]
            if selection:
                price = all_base_options[category][selection]
                choices[category] = PRICED_ITEM_FORMAT.format(f"{category.title()}: {selection.title()}", price)
            else:
                all_required_picked = False
                choices[category] = (f"*{category.title()}: PLEASE SELECT")
        
        toppings_price_sum = 0
        for topping_name in pizza["toppings"]:
            toppings_price_sum += all_toppings[topping_name]

        choices["$toppings"] = PRICED_ITEM_FORMAT.format(f"Toppings ({len(pizza['toppings'])} selected)", toppings_price_sum)

        total_price = calculate_pizza_price(pizza)
        if all_required_picked:
            choices["$exit"] = PRICED_ITEM_FORMAT.format("Finish", total_price)
        else:
            choices["$exit"] = "All unselected options (*) must be chosen to finish"
        
        choices["$cancel"] = "Cancel"

        choice = input_menu_indexed(choices, numbered=True, prompt="Modify pizza ingredients:\n")
        if choice == "$toppings":
            choose_toppings(pizza["toppings"], all_toppings)
        elif choice == "$exit":
            if all_required_picked:
                break
            else:
                print("Ingredients marked with an asterisk (*) are required, but not set. Select an option for all of them to finish this pizza.")
        elif choice == "$cancel":
            if pyip.inputYesNo("Cancel editing this pizza? (y/n) ") == "yes":
                return False
        else:
            choose_base_option(choice, all_base_options[choice], pizza["base_options"])

    if pizza["recipient"]:
        pizza["recipient"] = pyip.inputStr(f"Who is this pizza for? ({pizza["recipient"]})", blank=True) or pizza["recipient"]
    else:
        pizza["recipient"] = pyip.inputStr(f"Who is this pizza for? ")

    return True

def calculate_pizza_price(pizza):
    price_sum = 0
    for category in all_base_options.keys():
        selection = pizza["base_options"][category]
        if selection:
            price_sum += all_base_options[category][selection]
    
    for topping_name in pizza["toppings"]:
        price_sum += all_toppings[topping_name]

    return price_sum

def command_new():
    pizza = {
        "base_options": {},
        "toppings": [],
        "recipient": ""
    }

    for category in all_base_options.keys():
        pizza["base_options"][category] = None
    
    if edit_pizza(pizza):
        cart.append(pizza)

def command_edit():
    if not cart:
        print("No items in cart!")
        return
    while True:
        choices = {}

        for i, pizza in enumerate(cart):
            choices[i] = PRICED_ITEM_FORMAT.format(pizza["recipient"].title() + "'s pizza", calculate_pizza_price(pizza))
        
        choices["$back"] = "Back"

        choice = input_menu_indexed(choices, numbered=True)

        if choice == "$back":
            return
        else:
            pizza = cart[choice]
            edit_pizza(pizza)

def command_remove():
    if not cart:
        print("No items in cart!")
        return
    while True:
        choices = {}

        for i, pizza in enumerate(cart):
            choices[i] = PRICED_ITEM_FORMAT.format(pizza["recipient"].title() + "'s pizza", calculate_pizza_price(pizza))
        
        choices["$back"] = "Back"

        choice = input_menu_indexed(choices, numbered=True)

        if choice == "$back":
            return
        else:
            pizza = cart[choice]
            if pyip.inputYesNo(f"Remove {pizza['recipient'].title()}'s pizza? (y/n) ") == "yes":
                cart.pop(choice)

def command_checkout():
    if not cart:
        print("No items in cart!")
        return False
    
    total_price = 0

    for i, pizza in enumerate(cart):
        print("=" * 58)
        print(f"Pizza #{i + 1}")
        print("Recipient: " + pizza['recipient'].title())
        print("-" * 58)
        print_pizza_receipt(pizza)
        total_price += calculate_pizza_price(pizza)
    
    print("=" * 58)
    print(PRICED_ITEM_FORMAT.format("Grand total", total_price))
    print("=" * 58)

    return True

def print_pizza_receipt(pizza):
    for category, base_option in pizza["base_options"].items():
        # print out option name and price
        print(PRICED_ITEM_FORMAT.format(base_option.title(), all_base_options[category][base_option]))

    for topping in pizza["toppings"]:
        # print out topping name and price
        print(PRICED_ITEM_FORMAT.format("+ ADD " + topping.title(), all_toppings[topping]))
    
    print("-" * 58)
    print(PRICED_ITEM_FORMAT.format("Subtotal", calculate_pizza_price(pizza)))

def create_order():
    today = datetime.today()
    order_id = f"{today.year:>04}{today.month:>02}{today.day:>02}_{today.hour:>02}{today.minute:>02}{today.second:>02}"

    # find a suitable file location for the order
    order_filepath = Path.joinpath(ORDERS_DIRECTORY, Path(order_id + ".json"))

    attempts = 0
    try:
        while Path.exists(order_filepath):
            order_filepath = Path.joinpath(ORDERS_DIRECTORY, Path(f"{order_id}_{attempts}.json"))
    except Exception as error:
        print("Failed to create order while looking for suitable file location")
        print(error)
        return False

    # create the order json string data
    order_file_data = json.dumps({
        "id": order_id,
        "date": today.isoformat(),
        "items": cart
    })

    # write the order data to the file location
    try:
        # create directories out to the order destination
        os.makedirs(os.path.dirname(order_filepath), exist_ok=True)

        with open(order_filepath, "w") as order_file:
            order_file.write(order_file_data)
    except Exception as error:
        print("Failed to create order file")
        print(error)
        return False
    
    print("Written order to " + str(order_filepath))
    return True


main()
