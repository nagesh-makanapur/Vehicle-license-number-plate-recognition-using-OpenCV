import cv2
import easyocr
import mysql.connector
from twilio.rest import Client
import numpy as np
import phonenumbers
from datetime import datetime
import requests  # To get geolocation from IP
import json

# Twilio Credentials (Removed for security)
TWILIO_ACCOUNT_SID = 'your_twilio_account_sid'  # Replace with your Twilio Account SID
TWILIO_AUTH_TOKEN = 'your_twilio_auth_token'  # Replace with your Twilio Auth Token
TWILIO_PHONE_NUMBER = 'your_twilio_phone_number'  # Twilio phone number for SMS (Ensure it's in E.164 format)

# MySQL Connection Setup (Removed for security)
db = mysql.connector.connect(
     host="127.0.0.1",  # Update with the IP address of the remote DB if it's not on the same machine
     user="root",  # Change to your MySQL username
     password="your_mysql_password",  # Change to your MySQL password
     database="TrafficViolations",
     port=3306  # Default MySQL port
     )
cursor = db.cursor()

# Initialize Twilio Client (Removed for security)
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Initialize EasyOCR Reader
reader = easyocr.Reader(['en'])

# Set Speed Limit (example: 50 km/h)
SPEED_LIMIT = 0  # Adjust as needed

# Function to get current GPS location using IP Geolocation
def get_current_location():
    try:
        # Query an IP geolocation API to get location based on public IP
        response = requests.get("http://ipinfo.io/json")  # IPinfo API (free tier)
        data = response.json()
        location = data.get("loc", "Not Available").split(",")
        city = data.get("city", "Unknown")
        region = data.get("region", "Unknown")
        country = data.get("country", "Unknown")
        return location, city, region, country
    except Exception as e:
        print(f"Error fetching location: {e}")
        return None, None, None, None

# Function to get owner's details (including owner's name)
def get_owner_details(license_plate):
    query = "SELECT owner_name, phone_number, violations_count, license_expiry_date, city, region, country FROM Owners WHERE license_plate = %s"
    cursor.execute(query, (license_plate,))
    result = cursor.fetchone()
    if result:
        owner_name, phone_number, violations_count, license_expiry_date, city, region, country = result
        print(f"Owner details: {owner_name}, Phone: {phone_number}, Violations: {violations_count}, License Expiry: {license_expiry_date}, Location: {city}, {region}, {country}")
        
        # Ensure phone number includes the correct country code (e.g., +91 for India)
        if not phone_number.startswith('+'):
            phone_number = '+91' + phone_number  # Prepending country code
        return owner_name, phone_number, violations_count, license_expiry_date, city, region, country
    return None, None, None, None, None, None, None

def send_sms_message(owner_name, license_plate, phone_number, violation_message):
    try:
        # Modify the message to include the owner's name
        full_message = f"Dear {owner_name},\n{violation_message}\nYour License Plate: {license_plate} has violated the speed limit."

        # Send SMS message to the phone number using Twilio
        message = client.messages.create(
            body=full_message,
            from_=TWILIO_PHONE_NUMBER,  # Twilio phone number
            to=phone_number  # Ensure phone_number is in the correct format (E.164)
        )
        print(f"SMS sent to {phone_number}: {message.sid}")
        print(f"Message status: {message.status}")  # Log message status
    except Exception as e:
        print(f"Failed to send SMS: {e}")  # Print any error encountered during sending the SMS

# Function to detect license plate using EasyOCR
def detect_license_plate(frame):
    # EasyOCR to detect text (including license plates)
    result = reader.readtext(frame)
    
    detected_text = None
    for (bbox, text, prob) in result:
        # Here we check if the OCR confidence is good enough (adjust the threshold as necessary)
        if prob > 0.5:  # Confidence threshold for valid detection
            detected_text = text.strip()
            print(f"Detected License Plate: {detected_text}")
            # Draw bounding box around the detected license plate
            # Convert bbox coordinates to integers for OpenCV
            top_left = tuple(map(int, bbox[0]))  # Ensure x, y are integers
            bottom_right = tuple(map(int, bbox[2]))  # Ensure x, y are integers
            cv2.rectangle(frame, top_left, bottom_right, (0, 255, 0), 2)
            cv2.putText(frame, detected_text, top_left, cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
    
    return detected_text

# Function to update the violation count
def update_violations_count(license_plate):
    # Get the current violation count from the Owners table
    query = "SELECT violations_count FROM Owners WHERE license_plate = %s"
    cursor.execute(query, (license_plate,))
    result = cursor.fetchone()
    
    if result:
        violations_count = result[0]
        # Increment the violation count
        violations_count += 1
        
        # Update the violation count in the Owners table
        query = "UPDATE Owners SET violations_count = %s WHERE license_plate = %s"
        cursor.execute(query, (violations_count, license_plate))
        db.commit()
        print(f"Violation count updated for plate: {license_plate}, new count: {violations_count}")
    else:
        print(f"Error: License plate {license_plate} not found. Violations count not updated.")

# Function to store violation and update count
def store_violation(license_plate, violation_message):
    # Check if the license plate exists in the Owners table
    query = "SELECT COUNT(*) FROM Owners WHERE license_plate = %s"
    cursor.execute(query, (license_plate,))
    result = cursor.fetchone()
    
    # If the license plate exists, insert the violation and update count
    if result[0] > 0:
        # Insert the violation into the Violations table
        query = "INSERT INTO Violations (license_plate, violation_message) VALUES (%s, %s)"
        cursor.execute(query, (license_plate, violation_message))
        db.commit()
        print(f"Violation stored in database for plate: {license_plate}")
        
        # Update violation count
        update_violations_count(license_plate)
    else:
        print(f"Error: License plate {license_plate} does not exist in the Owners table. Violation not stored.")

# Initialize video capture (webcam or video file)
cap = cv2.VideoCapture(0)  # 0 for webcam, or use the video file path

if not cap.isOpened():
    print("Error: Could not open video stream.")
    exit()

while True:
    # Capture frame-by-frame from the video stream
    ret, frame = cap.read()
    
    if not ret:
        print("Error: Failed to read frame.")
        break
    
    # Detect License Plate
    plate = detect_license_plate(frame)
    
    if plate:
        # Store the violation in the database
        violation_message = f"Speeding violation detected (over {SPEED_LIMIT} km/h)"
        store_violation(plate, violation_message)

        # Get current location from IP
        location, city, region, country = get_current_location()
        
        # Get owner's details
        owner_name, phone_number, violations_count, license_expiry_date, owner_city, owner_region, owner_country = get_owner_details(plate)
        
        if phone_number:
            violation_message = f"Traffic Violation Detected! License Plate: {plate} has violated the speed limit of {SPEED_LIMIT} km/h.\nLocation: {city}, {region}, {country}\nDate and Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\nViolation Message: {violation_message}"

            # Add GPS location to message
            if location != "Not Available":
                violation_message += f"\nCurrent GPS Location: Latitude: {location[0]}, Longitude: {location[1]}"

            # Check for license expiry date and add to message if expired
            if license_expiry_date and datetime.now().date() > license_expiry_date:
                violation_message += f"\nWarning: Your license has expired on {license_expiry_date}."

            # Check for violation count and add a warning if it exceeds 2
            if violations_count > 2:
                violation_message += "\nYour violations have reached the maximum limit!"

            # Send SMS with owner's name included
            send_sms_message(owner_name, plate, phone_number, violation_message)
        else:
            print(f"No phone number registered for license plate {plate}. No message sent.")
    
    # Display the live video with bounding box
    cv2.imshow('License Plate Detection - Real-Time', frame)
    
    # Break the loop if 'q' key is pressed
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Release the capture object and close the windows
cap.release()
cv2.destroyAllWindows()

# Release MySQL connection
cursor.close()
db.close()
