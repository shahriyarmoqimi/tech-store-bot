import os
import telebot
from flask import Flask, request, Response
from telebot import types
from db import execute_query, check_admin

# Initialize Bot and Flask App
TOKEN = os.environ.get('TELEGRAM_TOKEN')
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Temporary memory for user state (Note: Vercel is serverless, this resets frequently)
user_data = {}

# --- Keyboards ---
def main_menu_keyboard():
    markup = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
    btn1 = types.KeyboardButton("1. View All Products")
    btn2 = types.KeyboardButton("2. Edit Product Attributes")
    btn3 = types.KeyboardButton("3. Add New Product")
    markup.add(btn1, btn2, btn3)
    return markup

# --- Start & Login Handlers ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    msg = bot.reply_to(message, "Welcome! Please enter your username:")
    bot.register_next_step_handler(msg, get_username)

def get_username(message):
    chat_id = message.chat.id
    username = message.text
    user_data[chat_id] = {'username': username}
    msg = bot.reply_to(message, "Please enter your password:")
    bot.register_next_step_handler(msg, get_password)

def get_password(message):
    chat_id = message.chat.id
    password = message.text
    username = user_data.get(chat_id, {}).get('username')

    if check_admin(username, password):
        user_data[chat_id]['auth'] = True
        bot.send_message(chat_id, "✅ Login successful.", reply_markup=main_menu_keyboard())
    else:
        bot.send_message(chat_id, "❌ Invalid credentials. Type /start to try again.")

# --- Main Menu Logic ---
@bot.message_handler(func=lambda message: True)
def menu_handler(message):
    chat_id = message.chat.id
    
    # Check authentication
    if not user_data.get(chat_id, {}).get('auth'):
        bot.send_message(chat_id, "Please login first using /start")
        return

    text = message.text

    # Option 1: View Products
    if "View All Products" in text:
        query = "SELECT id, name, price, stock FROM products ORDER BY id ASC"
        products = execute_query(query, fetch=True)
        
        if products:
            response = "📦 **Product List:**\n\n"
            for p in products:
                response += f"🆔 ID: {p[0]}\n📌 Name: {p[1]}\n💰 Price: ${p[2]}\n🔢 Stock: {p[3]}\n----------------\n"
            bot.send_message(chat_id, response)
        else:
            bot.send_message(chat_id, "No products found.")

    # Option 2: Edit Attributes
    elif "Edit Product Attributes" in text:
        msg = bot.send_message(chat_id, "🆔 Please enter the Product ID you want to edit:")
        bot.register_next_step_handler(msg, process_edit_step1_pid)

    # Option 3: Add New Product
    elif "Add New Product" in text:
        msg = bot.send_message(chat_id, "📝 Enter the name of the new product:")
        bot.register_next_step_handler(msg, process_add_name)

# --- Edit Attribute Flow ---
def process_edit_step1_pid(message):
    try:
        product_id = int(message.text)
        chat_id = message.chat.id
        
        # Verify product exists
        check = execute_query("SELECT id FROM products WHERE id = %s", (product_id,), fetch_one=True)
        if not check:
            bot.send_message(chat_id, "❌ Product ID not found. Return to menu.")
            return

        user_data[chat_id]['edit_pid'] = product_id

        # Fetch all available attributes and their current values for this product
        query = """
            SELECT a.id, a.name, pa.value 
            FROM attributes a 
            LEFT JOIN product_attributes pa 
            ON a.id = pa.attribute_id AND pa.product_id = %s
            ORDER BY a.id ASC
        """
        attrs = execute_query(query, (product_id,), fetch=True)
        
        if not attrs:
            bot.send_message(chat_id, "No attributes defined in the system.")
            return

        text_msg = f"🔧 **Attributes for Product ID: {product_id}**\n\n"
        for a in attrs:
            val = a[2] if a[2] else "(Not Set)"
            text_msg += f"🔹 Attr ID: {a[0]} | Name: {a[1]} | Current Value: {val}\n"
        
        text_msg += "\n👇 Enter the **Attribute ID** you wish to change or add:"
        msg = bot.send_message(chat_id, text_msg)
        bot.register_next_step_handler(msg, process_edit_step2_aid)
        
    except ValueError:
        bot.send_message(message.chat.id, "❌ Error: ID must be a number.")

def process_edit_step2_aid(message):
    try:
        attr_id = int(message.text)
        user_data[message.chat.id]['edit_aid'] = attr_id
        msg = bot.send_message(message.chat.id, "✍️ Enter the new value for this attribute:")
        bot.register_next_step_handler(msg, process_edit_step3_value)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Error: Attribute ID must be a number.")

def process_edit_step3_value(message):
    new_value = message.text
    chat_id = message.chat.id
    pid = user_data[chat_id]['edit_pid']
    aid = user_data[chat_id]['edit_aid']
    
    # Upsert Logic: Insert if not exists, update if exists
    # Requires a UNIQUE constraint on (product_id, attribute_id) in the database
    query = """
        INSERT INTO product_attributes (product_id, attribute_id, value)
        VALUES (%s, %s, %s)
        ON CONFLICT (product_id, attribute_id) 
        DO UPDATE SET value = EXCLUDED.value;
    """
    
    result = execute_query(query, (pid, aid, new_value))
    
    if result:
        bot.send_message(chat_id, "✅ Attribute updated successfully.", reply_markup=main_menu_keyboard())
    else:
        bot.send_message(chat_id, "❌ Database error occurred.", reply_markup=main_menu_keyboard())

# --- Add Product Flow ---
def process_add_name(message):
    user_data[message.chat.id]['new_prod'] = {'name': message.text}
    msg = bot.send_message(message.chat.id, "💰 Enter the Price:")
    bot.register_next_step_handler(msg, process_add_price)

def process_add_price(message):
    user_data[message.chat.id]['new_prod']['price'] = message.text
    msg = bot.send_message(message.chat.id, "🔢 Enter the Stock Quantity:")
    bot.register_next_step_handler(msg, process_add_stock)

def process_add_stock(message):
    user_data[message.chat.id]['new_prod']['stock'] = message.text
    msg = bot.send_message(message.chat.id, "📝 Enter the Description:")
    bot.register_next_step_handler(msg, process_add_desc)

def process_add_desc(message):
    chat_id = message.chat.id
    desc = message.text
    prod = user_data[chat_id]['new_prod']
    
    query = """
        INSERT INTO products (name, description, price, stock)
        VALUES (%s, %s, %s, %s)
    """
    result = execute_query(query, (prod['name'], desc, prod['price'], prod['stock']))
    
    if result:
        bot.send_message(chat_id, "✅ Product created successfully!\nUse 'Edit Product Attributes' to add details.", reply_markup=main_menu_keyboard())
    else:
        bot.send_message(chat_id, "❌ Failed to create product.", reply_markup=main_menu_keyboard())

# --- Vercel Webhook Handler ---
@app.route('/api/index', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return Response('OK', status=200)
    else:
        return Response('Access Denied', status=403)

@app.route('/')
def index():
    return "Bot is running.", 200
