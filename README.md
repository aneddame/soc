Flask Remote File Executor
This project is a Flask-based web application for managing and executing files remotely on connected devices like Raspberry Pi, Odroid, and others via SSH. The application supports queuing, differentiates admin and client requests, and executes Python, C, C++, or binary files directly on remote devices.

Features:
Device Management: Execute files on multiple devices (Raspberry Pi, Odroid, or custom devices).
Queue System: Prioritize files based on admin or client status.
File Execution: Supports .py, .c, .cpp, .out, and other executable files.
SSH Integration: Securely transfer and execute files via SSH.
Execution Time Tracking: Displays detailed output, errors, and execution time for each executed file.
Web Interface: Simple web UI to upload files and view execution results.
Requirements:
Python 3.x
Flask
Paramiko
SSH-enabled devices
Usage:
Clone the repository.
Install the required Python packages.
Configure device credentials and MAC addresses in the script.
Start the Flask server to upload and execute files remotely.
