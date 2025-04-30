import boto3
import subprocess
import json
import os
import urllib.error
import urllib.request

from flask import Flask, redirect, url_for, request, flash, send_file, abort
from flask import render_template
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

#load the env variables
load_dotenv()

from s3 import s3_upload_files, list_s3_objects, delete_objects, download_objects

application = Flask(__name__)

try:
    token = subprocess.run(["curl", "--request", "PUT", "http://169.254.169.254/latest/api/token", "--header", "X-aws-ec2-metadata-token-ttl-seconds: 3600"], check=True, stdout=subprocess.PIPE, universal_newlines=True).stdout.strip()
    instance_metadata = subprocess.run(["curl", "-s", "http://169.254.169.254/latest/dynamic/instance-identity/document", "--header", f"X-aws-ec2-metadata-token: {token}"], check=True, stdout=subprocess.PIPE, universal_newlines=True).stdout
    
    if instance_metadata:
        metadata = json.loads(instance_metadata)
        instance_id = metadata["instanceId"]
        region = metadata["region"]
        application.config["REGION"] = region
  
        ec2 = boto3.resource("ec2", region_name=region)
        instance = ec2.Instance(instance_id)
        instance_name = next((tag["Value"] for tag in instance.tags if tag["Key"] == "Name"), "")
        application.config["INSTANCE_NAME"] = instance_name
    else:
        region = "us-east-1"
        application.config["REGION"] = "unknown region"
        application.config["INSTANCE_NAME"] = "unknown name"

except subprocess.CalledProcessError as e:
    print(f"Error: {e}")
    instance_id = None
    region = None
    instance_name = None

query_count = 0
application.secret_key = os.urandom(24)
application.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
ALLOWED_EXTENSIONS = {'jpg', 'png'}
dynamodb_client = boto3.client('dynamodb',region)
bucket_name = os.environ.get('BUCKET_NAME')


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def query_increment():
    global query_count
    query_count = query_count + 1


@application.route('/', methods=['GET', 'POST'])
def index():
    if request.method in 'POST':
        print(f"*** Inside the template")
    if list_s3_objects(bucket_name):
        return redirect(url_for('files'))
    else:
        return render_template('main.html')


@application.route('/files')
def files():
    results = list_s3_objects(bucket_name)
    if results:
        query_increment()
        try:
            forms = dynamodb_client.execute_statement(Statement="SELECT * from forms;")
            entries = forms['Items']
            return render_template('files.html', files=results, entries=entries)
        except Exception as e:
            print(f"error:{e}")
            return render_template('files.html', files=results)
    else:
        return render_template('main.html')


@application.route('/upload_files_to_s3', methods=['GET', 'POST'])
def upload_files_to_s3():
    if request.method == 'POST':

        # No file selected
        if 'file' not in request.files:
            flash(f' *** No files Selected', 'danger')

        file_to_upload = request.files['file']
        content_type = request.mimetype

        # if empty files
        if file_to_upload.filename == '':
            flash(f' *** No files Selected', 'danger')

        # file uploaded and check
        if file_to_upload and allowed_file(file_to_upload.filename):

            file_name = secure_filename(file_to_upload.filename)

            print(f" *** The file name to upload is {file_name}")
            print(f" *** The file full path  is {file_to_upload}")

            s3_upload_files(file_to_upload, bucket_name, file_name, content_type)
            flash(f'Success - {file_to_upload} Is uploaded to {bucket_name} bucket', 'success')

        else:
            flash(f'Allowed file type are - jpg and png.Please upload proper formats...', 'danger')
            return redirect(url_for('files'))

    return redirect(url_for('files'))


@application.route('/delete_objects', methods=['POST'])
def delete():
    key = request.form['key']
    response = delete_objects(bucket_name, key)
    if response['ResponseMetadata']['HTTPStatusCode'] == 204:
        flash(f'Success - File Is Deleted from {bucket_name} bucket', 'success')
    else:
        flash(f'Could not delete the file...', 'danger')
        return render_template('main.html')

    if list_s3_objects(bucket_name):
        return redirect(url_for('files'))
    else:
        return render_template('main.html')


@application.route('/download_objects', methods=['POST'])
def download():
    key = request.form['key']
    response = download_objects(bucket_name, key)
    if response:
        flash(f'Success - File {key} Downloaded', 'success')
    else:
        flash(f'Could not download the file...', 'danger')
    return send_file(response, as_attachment=True)


@application.route("/<full_name>")
def items(full_name):
    print(full_name)
    query_increment()
    form_list = []
    item_query = dynamodb_client.execute_statement(Statement="SELECT * from forms;")
    for c in item_query['Items']:
        name = c.get('Full Name:').get('S')
        if name == full_name:
            form_list.append(name)

    if len(form_list) < 1:
        abort(404)

    query_increment()
    form_data = dynamodb_client.execute_statement(Statement="SELECT * from forms;")
    items_data = form_data['Items']
    return render_template('query.html', items=items_data)


def query_increment():
    global query_count
    query_count = query_count + 1


# run the app.
if __name__ == "__main__":
    # Setting debug to True enables debug output. This line should be
    # removed before deploying a production app.
    application.debug = True
    application.run(host='0.0.0.0', port=8443)
