@echo off
echo 🚨 EMERGENCY ORDER CANCELLATION
echo ================================
echo.
echo This will help resolve infinite order loops
echo by cancelling all pending orders.
echo.
echo WARNING: This affects your actual trading account!
echo.
pause
echo.
python emergency_order_manager.py
pause
