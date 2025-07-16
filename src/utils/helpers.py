"""Helper utilities and common functions"""

import re
import uuid
import hashlib
from typing import Any, Optional, Union, List
from datetime import datetime, date, timedelta
from decimal import Decimal
import bleach
import holidays

def generate_id(prefix: str = "", length: int = 8) -> str:
    """Generate unique ID with optional prefix"""
    unique_id = str(uuid.uuid4()).replace('-', '')[:length]
    return f"{prefix}_{unique_id}" if prefix else unique_id

def generate_hash(data: str, algorithm: str = "sha256") -> str:
    """Generate hash for data"""
    if algorithm == "md5":
        return hashlib.md5(data.encode()).hexdigest()
    elif algorithm == "sha1":
        return hashlib.sha1(data.encode()).hexdigest()
    elif algorithm == "sha256":
        return hashlib.sha256(data.encode()).hexdigest()
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")

def format_currency(amount: Union[int, float, Decimal], currency: str = "USD") -> str:
    """Format currency with proper symbols and formatting"""
    symbols = {
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
        "JPY": "¥",
        "VND": "₫"
    }
    
    symbol = symbols.get(currency, currency)
    
    if currency == "JPY":
        # Japanese Yen has no decimal places
        return f"{symbol}{amount:,.0f}"
    elif currency == "VND":
        # Vietnamese Dong formatting
        return f"{amount:,.0f} {symbol}"
    else:
        # Standard formatting with 2 decimal places
        return f"{symbol}{amount:,.2f}"

def validate_email(email: str) -> bool:
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def validate_phone(phone: str, country_code: str = "US") -> bool:
    """Validate phone number format"""
    # Remove all non-digit characters
    digits_only = re.sub(r'\D', '', phone)
    
    if country_code == "US":
        # US phone number: 10 digits
        return len(digits_only) == 10
    elif country_code == "VN":
        # Vietnamese phone number: 9-11 digits
        return 9 <= len(digits_only) <= 11
    else:
        # International: 7-15 digits
        return 7 <= len(digits_only) <= 15

def parse_date(date_string: str, formats: List[str] = None) -> Optional[date]:
    """Parse date string with multiple format attempts"""
    if formats is None:
        formats = [
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%d/%m/%Y",
            "%Y-%m-%d %H:%M:%S",
            "%m/%d/%Y %H:%M:%S",
            "%B %d, %Y",
            "%d %B %Y"
        ]
    
    for fmt in formats:
        try:
            parsed = datetime.strptime(date_string, fmt)
            return parsed.date()
        except ValueError:
            continue
    
    return None

def sanitize_string(text: str, allowed_tags: List[str] = None) -> str:
    """Sanitize string by removing dangerous content"""
    if allowed_tags is None:
        allowed_tags = ['b', 'i', 'u', 'em', 'strong']
    
    # Use bleach to clean HTML
    cleaned = bleach.clean(text, tags=allowed_tags, strip=True)
    
    # Remove excessive whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    return cleaned

def normalize_text(text: str) -> str:
    """Normalize text for comparison and search"""
    # Convert to lowercase
    normalized = text.lower()
    
    # Remove special characters but keep spaces
    normalized = re.sub(r'[^\w\s]', '', normalized)
    
    # Replace multiple spaces with single space
    normalized = re.sub(r'\s+', ' ', normalized)
    
    # Strip leading/trailing whitespace
    normalized = normalized.strip()
    
    return normalized

def calculate_business_days(start_date: date, end_date: date, country: str = "US") -> int:
    """Calculate business days between two dates"""
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    
    # Get holidays for the country
    country_holidays = holidays.country_holidays(country)
    
    business_days = 0
    current_date = start_date
    
    while current_date <= end_date:
        # Check if it's a weekday (Monday=0, Sunday=6)
        if current_date.weekday() < 5:  # Monday to Friday
            # Check if it's not a holiday
            if current_date not in country_holidays:
                business_days += 1
        
        current_date += timedelta(days=1)
    
    return business_days

def calculate_age(birth_date: date, reference_date: date = None) -> int:
    """Calculate age in years"""
    if reference_date is None:
        reference_date = date.today()
    
    age = reference_date.year - birth_date.year
    
    # Adjust for birthday not yet occurred this year
    if reference_date.month < birth_date.month or \
       (reference_date.month == birth_date.month and reference_date.day < birth_date.day):
        age -= 1
    
    return age

def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate text to maximum length with optional suffix"""
    if len(text) <= max_length:
        return text
    
    # Account for suffix length
    effective_length = max_length - len(suffix)
    
    if effective_length <= 0:
        return suffix[:max_length]
    
    return text[:effective_length] + suffix

def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    """Split list into chunks of specified size"""
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]

def flatten_dict(d: dict, parent_key: str = '', sep: str = '.') -> dict:
    """Flatten nested dictionary"""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

def deep_merge_dicts(dict1: dict, dict2: dict) -> dict:
    """Deep merge two dictionaries"""
    result = dict1.copy()
    
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_dicts(result[key], value)
        else:
            result[key] = value
    
    return result

def safe_get_nested(data: dict, keys: str, default: Any = None, separator: str = '.') -> Any:
    """Safely get nested dictionary value using dot notation"""
    try:
        result = data
        for key in keys.split(separator):
            result = result[key]
        return result
    except (KeyError, TypeError, AttributeError):
        return default

def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"

def is_business_day(check_date: date, country: str = "US") -> bool:
    """Check if date is a business day"""
    # Check if it's a weekday
    if check_date.weekday() >= 5:  # Saturday or Sunday
        return False
    
    # Check if it's a holiday
    country_holidays = holidays.country_holidays(country)
    return check_date not in country_holidays

def get_next_business_day(start_date: date, country: str = "US") -> date:
    """Get next business day after given date"""
    next_day = start_date + timedelta(days=1)
    
    while not is_business_day(next_day, country):
        next_day += timedelta(days=1)
    
    return next_day

def mask_sensitive_data(data: str, mask_char: str = "*", visible_chars: int = 4) -> str:
    """Mask sensitive data keeping only specified number of characters visible"""
    if len(data) <= visible_chars:
        return mask_char * len(data)
    
    visible_part = data[-visible_chars:]
    masked_part = mask_char * (len(data) - visible_chars)
    
    return masked_part + visible_part