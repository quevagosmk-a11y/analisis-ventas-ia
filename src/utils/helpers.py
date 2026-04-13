def format_sales_data(sales_data):
    formatted_data = []
    for sale in sales_data:
        formatted_data.append(
            {
                "product_id": sale["product_id"],
                "product_name": sale["product_name"],
                "quantity_sold": sale["quantity_sold"],
                "total_sales": sale["total_sales"],
                "sale_date": sale["sale_date"].strftime("%Y-%m-%d"),
            }
        )
    return formatted_data


def calculate_total_sales(sales_data):
    total = sum(sale["total_sales"] for sale in sales_data)
    return total


def get_top_selling_product(sales_data):
    if not sales_data:
        return None
    top_product = max(sales_data, key=lambda x: x["quantity_sold"])
    return top_product


def generate_sales_report(sales_data):
    report = {
        "total_sales": calculate_total_sales(sales_data),
        "top_product": get_top_selling_product(sales_data),
        "sales_count": len(sales_data),
    }
    return report
