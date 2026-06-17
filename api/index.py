from flask import Flask, render_template, request, session, redirect


app = Flask(__name__, 
            template_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), '../templates')),
            static_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), '../static')))

from flask_session import Session  # Required for large file data
import pandas as pd
import io
import base64
import matplotlib
matplotlib.use('Agg') 
import matplotlib.pyplot as plt

app.secret_key = 'your_secret_key_here' 

# ✅ Configure Server-Side Session (Fixes the "Cookie too large" crash)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

@app.route("/", methods=["GET", "POST"])
def home():
    changetext = "Please upload a CSV or Excel file"
    
    # 1. Initialize variables to prevent "Local Variable" errors
    total_revenue = session.get('total_revenue', 0)
    revenue_list = session.get('revenue_list', [])
    total_order = session.get('total_order', 0)
    average_revenue = session.get('average_revenue', 0)
    max_revenue = session.get('max_revenue', 0)
    status_list = session.get('status_list', [])

    if request.method == "POST":
        if "file" in request.files:
            file = request.files["file"]
            if file.filename != "":
                try:
                    filename = file.filename.lower()
                    if filename.endswith(".csv"):
                        # Added low_memory=False to stop DtypeWarnings
                        df = pd.read_csv(file, low_memory=False)
                    elif filename.endswith((".xls", ".xlsx")):
                        df = pd.read_excel(file)
                    
                    # Identify Columns
                    sales_col = session.get('custom_sales_col') or ('SALES' if 'SALES' in df.columns else 'Amount')
                    order_col = session.get('custom_order_col') or ('ORDERNUMBER' if 'ORDERNUMBER' in df.columns else 'Order ID')
                    status_col = session.get('custom_status_col') or ('STATUS' if 'STATUS' in df.columns else 'status')
                    month_col = session.get('custom_month_col') or ('MONTH' if 'MONTH' in df.columns else 'Month')
                    quantity_col = session.get('custom_quantity_col') or ('QUANTITYORDERED' if 'QUANTITYORDERED' in df.columns else 'Quantity')
                    customer_name_col = session.get('custom_customer_name_col') or ('CUSTOMERNAME' if 'CUSTOMERNAME' in df.columns else 'customername')
                    phone_col = session.get('custom_phone_col') or ('PHONE' if 'PHONE' in df.columns else 'phone')
                    address_col = session.get('custom_address_col') or ('ADDRESSADDRESSLINE1' if 'ADDRESSLINE1' in df.columns else 'address')


                    # Calculations
                    if sales_col in df.columns:
                        total_revenue = float(df[sales_col].sum().round(2))
                        revenue_list = df[sales_col].tolist()
                        average_revenue = float(df[sales_col].mean().round(2))
                        max_revenue = float(df[sales_col].max().round(2))

                    if order_col in df.columns:
                        total_order = int(df[order_col].value_counts().sum()) # Better: count unique orders
                        order_id = df[order_col].tolist()
                        repeated_orders = df[df[order_col].duplicated(keep=False)][order_col].unique()
                    
                    if month_col in df.columns:
                        month_list = df[month_col].tolist()  # Get month counts as a dictionary

                    if quantity_col in df.columns:
                        quantity_list = df[quantity_col].value_counts()

                    if status_col in df.columns:
                        status_list = df[status_col].fillna("Unknown").tolist()

                    if customer_name_col in df.columns:
                        customer_list = df[customer_name_col].fillna("Guest").tolist()

                    if phone_col in df.columns:
                        clean_phone = df[phone_col].tolist()

                    if address_col in df.columns:
                        address_list = df[address_col].fillna("No Address").tolist()
                        

                    # ✅ SAVE TO SERVER-SIDE SESSION
                    session['total_revenue'] = total_revenue
                    session['revenue_list'] = revenue_list
                    session['total_order'] = total_order
                    session['average_revenue'] = average_revenue
                    session['max_revenue'] = max_revenue
                    session['status_list'] = status_list
                    session['repeated_orders'] = repeated_orders
                    session['order_id'] = order_id
                    session['month_list'] = month_list
                    session['quantity_list'] = quantity_list
                    session['customer_list'] = customer_list
                    session['clean_phone'] = clean_phone
                    session['address_list'] = address_list
                    session['changetext'] = f"{file.filename} loaded!"

                except Exception as e:
                    session['changetext'] = f"Error: {e}"

    return render_template(
        "index.html",
        changetext=session.get('changetext', changetext),
        total_revenue=total_revenue,
        revenue_list=revenue_list[:6], 
        total_order=total_order,
        average_revenue=average_revenue,
        max_revenue=max_revenue
    )

@app.route('/revenue-detail')
def revenue_detail():
    revenue_list = session.get('revenue_list', [])
    total_revenue = session.get('total_revenue', 0)
    
    plot_url = ""
    if revenue_list:
        plt.figure(figsize=(10, 5))
        plt.plot(revenue_list, color='#0984e3', marker='o', linewidth=2, markersize=6)
        plt.title('Revenue Growth Trend')
        plt.grid(True, linestyle='--', alpha=0.6)
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plot_url = base64.b64encode(buf.getvalue()).decode('utf-8')
        plt.close()

    return render_template('revenue_page.html', 
                           plot_url=plot_url, 
                           revenue_list=revenue_list, 
                           total_revenue=total_revenue)

@app.route('/order-detail')
def order_detail():
    # 1. Get lists from session
    revenue_list = session.get('revenue_list', [])
    status_list = session.get('status_list', [])
    order_id_list = session.get('order_id', [])  # This is the full list of IDs
    month_list = session.get('month_list', [])
    quantity_list = session.get('quantity_list', [])
    customer_list = session.get('customer_list', []) # Ensure this is saved in upload
    clean_phone = session.get('clean_phone', []) # Ensure this is saved in upload
    custom_email = session.get('custom_email', [])
    address_list = session.get('address_list', [])

    # 2. Identify repeat logic based on Order IDs
    from collections import Counter
    id_counts = Counter(order_id_list)

    orders = []
    # 3. Use the loop to build each row one by one
    for i in range(len(order_id_list)):
        # Safely get item from each list using index i
        this_id = order_id_list[i] if i < len(order_id_list) else "N/A"
        this_status = status_list[i] if i < len(status_list) else "N/A"
        this_month = month_list[i] if i < len(month_list) else "N/A"
        this_qty = quantity_list[i] if i < len(quantity_list) else 0
        this_phone = clean_phone[i] if i < len(clean_phone) else "N/A"
        this_email = custom_email[i] if i < len(custom_email) else "N/A"
        this_address = address_list[i] if i < len(address_list) else "N/A"
        # Replace your current line with this to debug
        this_cust = customer_list[i] if (customer_list and i < len(customer_list)) else f"Missing: {session.get('cust_name_col')}"
    
        # Determine if it is a repeat order
        is_repeat = id_counts[this_id] > 1

        orders.append({
            'id': this_id,
            'amount': revenue_list[i],
            'customer': this_cust,
            'customer_type': 'repeat' if is_repeat else 'new', # Matching HTML logic
            'status': this_status,
            'date': this_month,
            'quantity': this_qty,
            'contact_info': this_phone,
            'contact_info': this_email,
            'address': this_address
        })

    return render_template('order_page.html', orders=orders, total_count=len(orders), this_cust=this_cust, this_id=this_id, this_phone=this_phone,
                           this_email=this_email, this_address=this_address)



@app.route("/setup_columns", methods=["GET", "POST"])
def setup_columns():
    if request.method == "POST":
        # Get the names from the form
        custom_sales = request.form.get("sales_col")
        custom_order = request.form.get("order_col")
        custom_date = request.form.get("date_col")
        custom_status = request.form.get("status_col")
        custom_customer = request.form.get("customer_name_col")
        custom_phone = request.form.get("phone_col")
        custom_email = request.form.get("email_col")
        custom_address = request.form.get("address_col")

        

        
        
        # Save them to session so the Home route can use them later
        session['custom_sales_col'] = custom_sales
        session['custom_order_col'] = custom_order
        session['custom_date_col'] = custom_date
        session['custom_status_col'] = custom_status
        session['custom_customer_name_col'] = custom_customer
        session['custom_phone_col'] = custom_phone
        session['custom_email_col'] = custom_email
        session['custom_address_col'] = custom_address
        session['changetext'] = f"Columns set to: {custom_sales} & {custom_order} & {custom_date}"

        return redirect("/") # Go back to dashboard
        
    return render_template("setup_columns.html")


@app.route("/average-revenue")
def average_revenue():
    # 1. Pull data from session
    revenue_list = session.get('revenue_list', [])
    total_revenue = session.get('total_revenue', 0)
    average_val = session.get('average_revenue', 0)
    total_order = session.get('total_order', 0)
    
    # Use the logic from your previous fixed order_detail to build 'orders'
    order_id_list = session.get('order_id_list', [])
    customer_list = session.get('customer_list', [])
    status_list = session.get('status_list', [])

    plot_url = ""
    if revenue_list:
        # 1. Calculate the average
        avg_value = sum(revenue_list) / len(revenue_list)

        plt.figure(figsize=(10, 5))
        
        # Plot the main revenue line
        plt.plot(revenue_list, color='#0984e3', marker='o', linewidth=2, markersize=6, label='Revenue')
        
        # 2. Add the highlight line for Average
        plt.axhline(y=avg_value, color='#d63031', linestyle='--', linewidth=2, label=f'Avg: ${avg_value:,.2f}')
        
        # 3. Add a background "fill" to highlight everything above the average (Optional but looks great)
        plt.fill_between(range(len(revenue_list)), revenue_list, avg_value, 
                         where=(pd.Series(revenue_list) > avg_value), 
                         interpolate=True, color='#55efc4', alpha=0.3, label='Above Average')

        plt.title('Revenue Analysis: Performance vs Average')
        plt.legend(loc='upper left')
        plt.grid(True, linestyle='--', alpha=0.4)
        plt.tight_layout()
        
        # Save to buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plot_url = base64.b64encode(buf.getvalue()).decode('utf-8')
        plt.close()
    
    orders = []
    for i in range(len(revenue_list)):
        orders.append({
            'id': order_id_list[i] if i < len(order_id_list) else "N/A",
            'amount': revenue_list[i],
            'customer': customer_list[i] if i < len(customer_list) else "Guest",
            'status': status_list[i] if i < len(status_list) else "N/A"
        })

    # Sort by highest revenue for the table
    orders = sorted(orders, key=lambda x: x['amount'], reverse=True)

    return render_template(
        "average_revenue.html", 
        average_revenue=f"{average_val:,.2f}",
        total_revenue=f"{total_revenue:,.2f}",
        total_order=total_order,
        orders=orders,
        plot_url=plot_url
    )



@app.route("/max-revenue")
def max_revenue_page():
    revenue_list = session.get('revenue_list', [])
    order_id_list = session.get('order_id_list', [])
    customer_list = session.get('customer_list', [])
    month_list = session.get('month_list', [])

    if not revenue_list:
        return redirect("/")

    # Build full order objects
    orders = []
    for i in range(len(revenue_list)):
        orders.append({
            'id': order_id_list[i] if i < len(order_id_list) else "N/A",
            'amount': revenue_list[i],
            'customer': customer_list[i] if i < len(customer_list) else "Guest",
            'month': month_list[i] if i < len(month_list) else "N/A"
        })

    # Sort to get Top 5 and the absolute Max
    sorted_orders = sorted(orders, key=lambda x: x['amount'], reverse=True)
    top_order = sorted_orders[0]
    top_5 = sorted_orders[:5]

    # Create Plot highlighting the MAX point
    plt.figure(figsize=(10, 4))
    plt.plot(revenue_list, color='#bdc3c7', alpha=0.5, label='Regular Sales')
    
    # Highlight the max point in Gold
    max_idx = revenue_list.index(max(revenue_list))
    plt.scatter(max_idx, max(revenue_list), color='#f1c40f', s=150, zorder=5, label='Max Record')
    plt.axhline(y=max(revenue_list), color='#f1c40f', linestyle=':', alpha=0.6)
    
    plt.title("Revenue Trend with Peak Highlight")
    plt.legend()
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plot_url = base64.b64encode(buf.getvalue()).decode('utf-8')
    plt.close()

    return render_template("max_revenue.html", 
                           max_revenue=f"{top_order['amount']:,.2f}",
                           top_order=top_order,
                           top_5=top_5,
                           plot_url=plot_url)

@app.route("/reset")
def reset_app():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    app.run(host="0.0.0.0" debug=False)