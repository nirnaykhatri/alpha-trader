#!/usr/bin/env python3
"""
Demo script to show how the market data provider handles different trading sessions
"""

import sys
sys.path.append('src')

from datetime import datetime, time
import pytz

def demo_market_sessions():
    """Demonstrate different market sessions and their behavior"""
    
    market_tz = pytz.timezone('US/Eastern')
    
    # Define test times
    test_times = [
        (2, 0),   # 2:00 AM - Closed
        (6, 0),   # 6:00 AM - Pre-market
        (10, 30), # 10:30 AM - Regular hours
        (15, 30), # 3:30 PM - Regular hours
        (17, 30), # 5:30 PM - After-hours
        (21, 0),  # 9:00 PM - Closed
    ]
    
    print("Market Session Demo:")
    print("==================")
    
    for hour, minute in test_times:
        # Create a test datetime for today
        test_time = datetime.now(market_tz).replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # Determine session
        session = get_session_for_time(test_time)
        is_open = session != 'closed'
        
        print(f"{test_time.strftime('%H:%M')} ET - Session: {session:12} - Trading: {'YES' if is_open else 'NO'}")
    
    print("\nKey Points:")
    print("- Pre-market: 4:00 AM - 9:30 AM (can execute trades)")
    print("- Regular: 9:30 AM - 4:00 PM (full trading)")
    print("- After-hours: 4:00 PM - 8:00 PM (can execute trades)")
    print("- Closed: 8:00 PM - 4:00 AM + weekends (no trading)")

def get_session_for_time(dt):
    """Get market session for a given datetime"""
    if dt.weekday() >= 5:  # Weekend
        return 'closed'
    
    hour = dt.hour
    minute = dt.minute
    current_minutes = hour * 60 + minute
    
    pre_market_start = 4 * 60  # 4:00 AM
    regular_start = 9 * 60 + 30  # 9:30 AM
    regular_end = 16 * 60  # 4:00 PM
    after_hours_end = 20 * 60  # 8:00 PM
    
    if pre_market_start <= current_minutes < regular_start:
        return 'pre-market'
    elif regular_start <= current_minutes < regular_end:
        return 'regular'
    elif regular_end <= current_minutes < after_hours_end:
        return 'after-hours'
    else:
        return 'closed'

if __name__ == "__main__":
    demo_market_sessions()
    
    print(f"\nCurrent Status:")
    market_tz = pytz.timezone('US/Eastern')
    now = datetime.now(market_tz)
    current_session = get_session_for_time(now)
    print(f"Time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"Session: {current_session}")
    print(f"Can trade: {'YES' if current_session != 'closed' else 'NO'}")
