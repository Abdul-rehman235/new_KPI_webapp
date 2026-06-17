from flask import Flask, render_template, request, session, redirect
from flask_session import Session  # Required for large file data
import pandas as pd
import io
import os
import tempfile
import base64
from collections import Counter
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


app = Flask(__name__,
            template_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), '../templates')),
            static_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), '../static')))


app.secret_key = 'your_secret_key_here'

# ✅ Configure Server-Side Session
# IMPORTANT (Vercel): the filesystem is READ-ONLY everywhere except /tmp.
# Flask-Session's default cache folder ("./flask_session") cannot be created
# on Vercel, which is what was causing FUNCTION_INVOCATION_FAILED on every
# single request (even GET /). Pointing it at the OS temp dir fixes that.
SESSION_DIR = os.path.join(tempfile.gettempdir(), 'flask_session')
os.makedirs(SESSION_DIR, exist_ok=True)

app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = SESSION_DIR
Session(app)

# NOTE: /tmp on serverless platforms is not guaranteed to persist between
# requests (a request can land on a fresh container with an empty /tmp).
# This stops the crash, but if you see data "disappearing" between pages
# after this fix, it means a request hit a different instance. For a fully
# reliable production setup on Vercel, swap SESSION_TYPE to a real external
# store (e.g. Redis via Vercel KV / Upstash) instead of "filesystem".


def get_col(custom_key, default_candidates, df):
    """Pick a column name: explicit user choice > first matching default name in df > fallback."""
    custom = session.get(custom_key)
    if custom:
        return custom
    for candidate in default_candidates:
        if candidate in df.columns:
            return candidate
    return default_candidates[-1]


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

    if request.method == "POST" and "file" in request.files:
        file = request.files["file"]
        if file.filename != "":
            try:
                filename = file.filename.lower()
                if filename.endswith(".csv"):
                    # low_memory=False stops DtypeWarnings
                    df = pd.read_csv(file, low_memory=False)
                elif filename.endswith((".xls", ".xlsx")):
                    df = pd.read_excel(file)
                else:
                    raise ValueError("Unsupported file type. Please upload a .csv, .xls, or .xlsx file.")

                # Identify Columns
                sales_col = get_col('custom_sales_col', ['SALES', 'Amount'], df)
                order_col = get_col('custom_order_col', ['ORDERNUMBER', 'Order ID'], df)
                status_col = get_col('custom_status_col', ['STATUS', 'status'], df)
                month_col = get_col('custom_month_col', ['MONTH', 'Month'], df)
                quantity_col = get_col('custom_quantity_col', ['QUANTITYORDERED', 'Quantity'], df)
                customer_name_col = get_col('custom_customer_name_col', ['CUSTOMERNAME', 'customername'], df)
                phone_col = get_col('custom_phone_col', ['PHONE', 'phone'], df)
                address_col = get_col('custom_address_col', ['ADDRESSLINE1', 'address'], df)
                email_col = get_col('custom_email_col', ['EMAIL', 'email'], df)

                # 2. Defaults so nothing below can ever be an undefined variable
                order_id = []
                repeated_orders = []
                month_list = []
                quantity_list = []
                customer_list = []
                clean_phone = []
                address_list = []
                email_list = []

                # Calculations
                if sales_col in df.columns:
                    total_revenue = float(df[sales_col].sum().round(2))
                    revenue_list = df[sales_col].tolist()
                    average_revenue = float(df[sales_col].mean().round(2))
                    max_revenue = float(df[sales_col].max().round(2))

                if order_col in df.columns:
                    total_order = int(df[order_col].nunique())  # distinct orders, not row count
                    order_id = df[order_col].tolist()
                    repeated_orders = df[df[order_col].duplicated(keep=False)][order_col].unique().tolist()

                if month_col in df.columns:
                    month_list = df[month_col].tolist()

                if quantity_col in df.columns:
                    quantity_list = df[quantity_col].tolist()  # per-row quantity, not value_counts

                if status_col in df.columns:
                    status_list = df[status_col].fillna("Unknown").tolist()

                if customer_name_col in df.columns:
                    customer_list = df[customer_name_col].fillna("Guest").tolist()

                if phone_col in df.columns:
                    clean_phone = df[phone_col].fillna("N/A").tolist()

                if address_col in df.columns:
                    address_list = df[address_col].fillna("No Address").tolist()

                if email_col in df.columns:
                    email_list = df[email_col].fillna("No Email").tolist()

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
                session['email_list'] = email_list
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
    order_id_list = session.get('order_id', [])
    month_list = session.get('month_list', [])
    quantity_list = session.get('quantity_list', [])
    customer_list = session.get('customer_list', [])
    clean_phone = session.get('clean_phone', [])
    email_list = session.get('email_list', [])
    address_list = session.get('address_list', [])

    # 2. Identify repeat logic based on Order IDs
    id_counts = Counter(order_id_list)

    orders = []
    # 3. Build each row safely using index i
    for i in range(len(order_id_list)):
        this_id = order_id_list[i]
        this_status = status_list[i] if i < len(status_list) else "N/A"
        this_month = month_list[i] if i < len(month_list) else "N/A"
        this_qty = quantity_list[i] if i < len(quantity_list) else 0
        this_phone = clean_phone[i] if i < len(clean_phone) else "N/A"
        this_email = email_list[i] if i < len(email_list) else "N/A"
        this_address = address_list[i] if i < len(address_list) else "N/A"
        this_cust = customer_list[i] if i < len(customer_list) else "Guest"

        is_repeat = id_counts[this_id] > 1

        orders.append({
            'id': this_id,
            'amount': revenue_list[i] if i < len(revenue_list) else 0,
            'customer': this_cust,
            'customer_type': 'repeat' if is_repeat else 'new',
            'status': this_status,
            'date': this_month,
            'quantity': this_qty,
            'phone': this_phone,
            'email': this_email,
            'address': this_address
        })

    return render_template('order_page.html', orders=orders, total_count=len(orders))


@app.route("/setup_columns", methods=["GET", "POST"])
def setup_columns():
    if request.method == "POST":
        custom_sales = request.form.get("sales_col")
        custom_order = request.form.get("order_col")
        custom_date = request.form.get("date_col")
        custom_status = request.form.get("status_col")
        custom_customer = request.form.get("customer_name_col")
        custom_phone = request.form.get("phone_col")
        custom_email = request.form.get("email_col")
        custom_address = request.form.get("address_col")

        session['custom_sales_col'] = custom_sales
        session['custom_order_col'] = custom_order
        session['custom_date_col'] = custom_date
        session['custom_status_col'] = custom_status
        session['custom_customer_name_col'] = custom_customer
        session['custom_phone_col'] = custom_phone
        session['custom_email_col'] = custom_email
        session['custom_address_col'] = custom_address
        session['changetext'] = f"Columns set to: {custom_sales} & {custom_order} & {custom_date}"

        return redirect("/")

    return render_template("setup_columns.html")


@app.route("/average-revenue")
def average_revenue():
    revenue_list = session.get('revenue_list', [])
    total_revenue = session.get('total_revenue', 0)
    average_val = session.get('average_revenue', 0)
    total_order = session.get('total_order', 0)

    order_id_list = session.get('order_id', [])  # was 'order_id_list' (key mismatch bug)
    customer_list = session.get('customer_list', [])
    status_list = session.get('status_list', [])

    plot_url = ""
    if revenue_list:
        avg_value = sum(revenue_list) / len(revenue_list)

        plt.figure(figsize=(10, 5))
        plt.plot(revenue_list, color='#0984e3', marker='o', linewidth=2, markersize=6, label='Revenue')
        plt.axhline(y=avg_value, color='#d63031', linestyle='--', linewidth=2, label=f'Avg: ${avg_value:,.2f}')
        plt.fill_between(range(len(revenue_list)), revenue_list, avg_value,
                          where=(pd.Series(revenue_list) > avg_value),
                          interpolate=True, color='#55efc4', alpha=0.3, label='Above Average')

        plt.title('Revenue Analysis: Performance vs Average')
        plt.legend(loc='upper left')
        plt.grid(True, linestyle='--', alpha=0.4)
        plt.tight_layout()

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
    order_id_list = session.get('order_id', [])  # was 'order_id_list' (key mismatch bug)
    customer_list = session.get('customer_list', [])
    month_list = session.get('month_list', [])

    if not revenue_list:
        return redirect("/")

    orders = []
    for i in range(len(revenue_list)):
        orders.append({
            'id': order_id_list[i] if i < len(order_id_list) else "N/A",
            'amount': revenue_list[i],
            'customer': customer_list[i] if i < len(customer_list) else "Guest",
            'month': month_list[i] if i < len(month_list) else "N/A"
        })

    sorted_orders = sorted(orders, key=lambda x: x['amount'], reverse=True)
    top_order = sorted_orders[0]
    top_5 = sorted_orders[:5]

    plt.figure(figsize=(10, 4))
    plt.plot(revenue_list, color='#bdc3c7', alpha=0.5, label='Regular Sales')

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


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)