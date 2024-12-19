import os
import time
import paramiko
from flask import Flask, request, redirect, render_template_string
from werkzeug.utils import secure_filename
from collections import deque

app = Flask(__name__)

# Define the list of IP addresses and their credentials
credentials = {
    'rpi1': {'ip': '172.16.45.212', 'username': 'pi', 'password': 'pi'},
    'rpi2': {'ip': '172.16.46.88', 'username': 'pi', 'password': 'pi'},
    'odroid': {'ip': '192.168.1.111', 'username': 'odroid', 'password': 'odroid'}
}

# Define the list of admin MAC addresses
admin_macs = ["90:2e:1c:48:c4:3e"]  # Add more admin MAC addresses as needed

# Define queues to hold files from admin and non-admin hosts
admin_queue = deque()
client_queue = deque()

# Global variable to store the results
execution_results = []

@app.route('/')
def home():
    return redirect('/queue')

@app.route('/queue')
def queue_page():
    return render_template_string('''
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <title>File Execution Results</title>
        <style>
            body { font-family: Arial, sans-serif; }
            .container { max-width: 800px; margin: auto; padding: 20px; }
            ul { list-style-type: none; padding: 0; }
            li { margin-bottom: 20px; padding: 10px; border: 1px solid #ccc; border-radius: 8px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>File Execution Results</h1>
            <ul>
            {% for result in execution_results %}
                <li>
                    <strong>{{ result['file_name'] }}</strong> on {{ result['device_choice'] }}<br>
                    MAC Address: {{ result['mac_address'] }}<br>
                    <pre>STDOUT: {{ result['stdout'] }}</pre>
                    <pre>STDERR: {{ result['stderr'] or 'No error output' }}</pre>
                    <pre>Execution Time: {{ result['execution_time'] }}</pre>
                </li>
            {% endfor %}
            </ul>
        </div>
    </body>
    </html>
    ''', execution_results=execution_results)

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'py', 'c', 'cpp', 'cl', 'cu', 'out'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/envoyer', methods=['POST'])
def envoyer_file():
    if 'file' not in request.files:
        return 'No file part', 400
    file = request.files['file']
    if file.filename == '':
        return 'No selected file', 400
    if file and allowed_file(file.filename):
        tmp_dir = '/tmp'
        os.makedirs(tmp_dir, exist_ok=True)

        file_name = secure_filename(file.filename)
        file_path = os.path.join(tmp_dir, file_name)
        file.save(file_path)

        device_choice = request.args.get('device')
        mac_address = request.args.get('mac')

        if device_choice in credentials or device_choice == 'other':
            if device_choice == 'other':
                other_ip = request.args.get('other_ip')
                other_username = request.args.get('other_username')
                other_password = request.args.get('other_password')
                creds = {'ip': other_ip, 'username': other_username, 'password': other_password}
            else:
                creds = credentials[device_choice]

            if mac_address in admin_macs:
                admin_queue.append((file_path, device_choice, mac_address, file_name, creds))
            else:
                client_queue.append((file_path, device_choice, mac_address, file_name, creds))

            process_next_file()
            return f'File {file.filename} uploaded and queued for execution'
        else:
            return 'Invalid device choice. Please choose from rpi1, rpi2, odroid, or other.', 400

    return 'Invalid file type. Only .py, .c, .cpp, .cl, .cu, and .out files are allowed.', 400

def process_next_file():
    try:
        if admin_queue:
            file_path, device_choice, mac_address, file_name, creds = admin_queue.popleft()
        elif client_queue:
            file_path, device_choice, mac_address, file_name, creds = client_queue.popleft()
        else:
            return

        send_file_to_device(file_path, device_choice, mac_address, file_name, creds)
    except Exception as e:
        print(f"Failed to process file: {e}")

def send_file_to_device(file_path, device_choice, mac_address, file_name, creds):
    try:
        username = creds['username']
        password = creds['password']
        device_ip = creds['ip']
        remote_path = '/home/pi/Desktop/' if username == 'pi' else '/home/odroid/Desktop/sesn'
        remote_file_path = os.path.join(remote_path, file_name)

        # Connect to the device via SSH
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(device_ip, username=username, password=password)

        # Upload the file to the remote device
        sftp = ssh.open_sftp()
        sftp.put(file_path, remote_file_path)
        sftp.close()

        stdout_data = ""
        stderr_data = ""
        start_time = time.time()  # Start timing

        # Execute the file based on its type
        if file_name.endswith('.py'):
            ssh.exec_command(f'chmod +x {remote_file_path}')
            stdin, stdout, stderr = ssh.exec_command(f'python3 {remote_file_path}')
        elif file_name.endswith('.c') or file_name.endswith('.cpp'):
            executable_name = file_name.rsplit('.', 1)[0]
            compiler = 'gcc' if file_name.endswith('.c') else 'g++'
            compile_command = (
                f'{compiler} -fopenmp -std=c++11 -o {os.path.join(remote_path, executable_name)} '
                f'{remote_file_path} -lOpenCL $(pkg-config --cflags --libs opencv4)'
            )
            stdin, stdout, stderr = ssh.exec_command(compile_command)
            compile_stderr = stderr.read().decode()

            if not compile_stderr:
                execution_command = f'{os.path.join(remote_path, executable_name)}'
                stdin, stdout, stderr = ssh.exec_command(execution_command)
            else:
                stdout_data = "Compilation Failed"
                stderr_data = compile_stderr
        elif file_name.endswith('.cl'):
            execution_command = f'python3 -m pyopencl {remote_file_path}'
            stdin, stdout, stderr = ssh.exec_command(execution_command)
        elif file_name.endswith('.out'):
            ssh.exec_command(f'chmod +x {remote_file_path}')
            stdin, stdout, stderr = ssh.exec_command(remote_file_path)
        else:
            stdout_data = "Unsupported file type"
            stderr_data = ""

        if not stdout_data and not stderr_data:
            stdout_data = stdout.read().decode()
            stderr_data = stderr.read().decode()

        end_time = time.time()  # End timing
        execution_time = end_time - start_time  # Calculate execution time

        execution_results.append({
            'file_name': file_name,
            'device_choice': device_choice,
            'mac_address': mac_address,
            'stdout': stdout_data,
            'stderr': stderr_data,
            'execution_time': f"{execution_time:.2f} seconds"
        })

        ssh.close()

    except Exception as e:
        print(f"Failed to send and execute file on device: {e}")
        execution_results.append({
            'file_name': file_name,
            'device_choice': device_choice,
            'mac_address': mac_address,
            'stdout': "",
            'stderr': f"Error: {e}",
            'execution_time': "N/A"
        })

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)

