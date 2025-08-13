"""
Payment utilities for currency conversion and gateway management
"""

def get_exchange_rates():
    """
    Get exchange rates for supported currencies
    In production, this would fetch from a real API like exchangerate-api.com
    """
    return {
        'USD': 1.0,
        'SAR': 3.75,
        'AED': 3.67,
        'EGP': 30.5,
        'EUR': 0.85,
        'GBP': 0.73,
        'INR': 83.0
    }

def get_currency_symbols():
    """Get currency symbols for display"""
    return {
        'USD': '$',
        'SAR': '﷼',
        'AED': 'د.إ',
        'EGP': 'ج.م',
        'EUR': '€',
        'GBP': '£',
        'INR': '₹'
    }

def convert_currency(amount, from_currency='USD', to_currency='USD'):
    """
    Convert amount from one currency to another
    """
    rates = get_exchange_rates()
    if from_currency == to_currency:
        return amount
    
    # Convert to USD first, then to target currency
    usd_amount = amount / rates.get(from_currency, 1.0)
    converted_amount = usd_amount * rates.get(to_currency, 1.0)
    
    return round(converted_amount, 2)

def get_gateway_config_template(gateway_type):
    """Get configuration template for different payment gateways"""
    templates = {
        'stripe': {
            'secret_key': '',
            'publishable_key': '',
            'webhook_secret': ''
        },
        'paypal': {
            'client_id': '',
            'client_secret': '',
            'webhook_id': ''
        },
        'paytabs': {
            'profile_id': '',
            'server_key': '',
            'client_key': ''
        },
        'razorpay': {
            'key_id': '',
            'key_secret': '',
            'webhook_secret': ''
        },
        'fawry': {
            'merchant_code': '',
            'security_key': '',
            'fawry_secure_key': ''
        },
        'paymob': {
            'api_key': '',
            'integration_id': '',
            'iframe_id': '',
            'hmac_secret': ''
        },
        'bank_transfer': {
            'bank_name': '',
            'account_number': '',
            'iban': '',
            'swift_code': '',
            'account_holder': ''
        }
    }
    
    return templates.get(gateway_type, {})

def get_supported_countries_by_gateway():
    """Get list of supported countries for each gateway"""
    return {
        'stripe': ['US', 'CA', 'GB', 'EU', 'SA', 'AE', 'EG', 'IN'],
        'paypal': ['US', 'CA', 'GB', 'EU', 'SA', 'AE', 'EG'],
        'paytabs': ['SA', 'AE', 'KW', 'BH', 'OM', 'QA', 'JO', 'EG'],
        'razorpay': ['IN', 'SA', 'AE', 'US'],
        'fawry': ['EG'],
        'paymob': ['EG', 'PK', 'NG'],
        'bank_transfer': ['SA', 'AE', 'EG', 'US', 'CA', 'GB'],
        'apple_pay': ['US', 'CA', 'GB', 'EU', 'SA', 'AE'],
        'google_pay': ['US', 'CA', 'GB', 'EU', 'SA', 'AE', 'IN'],
        'visa_direct': ['US', 'CA', 'GB', 'EU', 'SA', 'AE', 'EG'],
        'mastercard': ['US', 'CA', 'GB', 'EU', 'SA', 'AE', 'EG']
    }

def format_currency(amount, currency_code):
    """Format currency amount with proper symbol and decimal places"""
    symbols = get_currency_symbols()
    symbol = symbols.get(currency_code, currency_code)
    
    # Format with 2 decimal places
    formatted_amount = f"{amount:.2f}"
    
    # Some currencies use different formatting
    if currency_code in ['SAR', 'AED', 'EGP']:
        return f"{formatted_amount} {symbol}"
    else:
        return f"{symbol}{formatted_amount}"

def validate_payment_amount(amount, currency, gateway_type):
    """Validate if payment amount is within gateway limits"""
    # Convert to USD for comparison
    usd_amount = convert_currency(amount, currency, 'USD')
    
    # Gateway limits in USD
    limits = {
        'stripe': {'min': 0.50, 'max': 50000},
        'paypal': {'min': 1.00, 'max': 10000},
        'paytabs': {'min': 1.00, 'max': 10000},
        'razorpay': {'min': 1.00, 'max': 10000},
        'fawry': {'min': 1.00, 'max': 1000},  # Converted to USD equivalent
        'paymob': {'min': 1.00, 'max': 5000},
        'bank_transfer': {'min': 10.00, 'max': 100000}
    }
    
    gateway_limits = limits.get(gateway_type, {'min': 1.00, 'max': 10000})
    
    if usd_amount < gateway_limits['min']:
        return False, f"Minimum amount is {format_currency(convert_currency(gateway_limits['min'], 'USD', currency), currency)}"
    
    if usd_amount > gateway_limits['max']:
        return False, f"Maximum amount is {format_currency(convert_currency(gateway_limits['max'], 'USD', currency), currency)}"
    
    return True, "Amount is valid"

def get_processing_fee(amount, currency, gateway_type):
    """Calculate processing fee for different gateways"""
    # Fee percentages
    fees = {
        'stripe': 2.9,
        'paypal': 3.5,
        'paytabs': 2.75,
        'razorpay': 2.0,
        'fawry': 1.5,
        'paymob': 2.65,
        'bank_transfer': 0.0,
        'apple_pay': 2.9,
        'google_pay': 2.9,
        'visa_direct': 2.5,
        'mastercard': 2.5
    }
    
    fee_percent = fees.get(gateway_type, 2.9)
    fee_amount = (amount * fee_percent) / 100
    
    return round(fee_amount, 2)

def get_estimated_processing_time(gateway_type):
    """Get estimated processing time for different gateways"""
    times = {
        'stripe': {'en': 'Instant', 'ar': 'فوري'},
        'paypal': {'en': 'Instant', 'ar': 'فوري'},
        'paytabs': {'en': 'Instant', 'ar': 'فوري'},
        'razorpay': {'en': 'Instant', 'ar': 'فوري'},
        'fawry': {'en': '15 minutes', 'ar': '15 دقيقة'},
        'paymob': {'en': 'Instant', 'ar': 'فوري'},
        'bank_transfer': {'en': '1-3 business days', 'ar': '1-3 أيام عمل'},
        'apple_pay': {'en': 'Instant', 'ar': 'فوري'},
        'google_pay': {'en': 'Instant', 'ar': 'فوري'},
        'visa_direct': {'en': 'Instant', 'ar': 'فوري'},
        'mastercard': {'en': 'Instant', 'ar': 'فوري'}
    }
    
    return times.get(gateway_type, {'en': 'Instant', 'ar': 'فوري'})