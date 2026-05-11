import os
import subprocess
import pandas as pd

# Define the server name and upload path
upload_path = "/mnt/d/Xiaoman/001_mAb3D/05-E2/zarr_upload/Ab3D-E2-CA/"
inputlist = "/mnt/d/Xiaoman/001_mAb3D/05-E2/workfile/inputlist_E2_CA1-45.csv"

if 1:
  import argparse
  import json
  import tomllib as tomli

  parser = argparse.ArgumentParser(description='step 2')
  parser.add_argument('params', help='Path to JSON or TOML file containing project parameters')
  # Parse arguments
  args = parser.parse_args()

  # Load parameters from file
  params_path = args.params
  if params_path.endswith('.json'):
      with open(params_path, 'r') as f:
          params = json.load(f)
  elif params_path.endswith('.toml'):
      with open(params_path, 'rb') as f:
          params = tomli.load(f)
  else:
      raise ValueError("Parameter file must be .json or .toml")

  # Update global variables
  inputlist = params.get('worksheet') or params.get('inputlist')
  upload_path = params.get('zarr_dir') or params.get('omezarr_dir')


s3_bucket = 'mAb3D'
awsbucket_path = 's3://mAb3D/Zarr/'

aws_cli_profile = 'wulab'  # AWS CLI profile to use for endpoint and authentication

# Function to upload zarr file to AWS S3 bucket
def upload_to_s3(zarr_file, section_index):
    zarrpath = os.path.join(upload_path, zarr_file) + '/' + str(section_index) + '/'
    awspath = awsbucket_path + zarr_file + '/' + str(section_index) + '/'

    # aws_command = ['aws', '--endpoint-url', 'https://redcloud.cac.cornell.edu:8443/', '--no-verify', 's3', '--profile', 'CAC', 'cp',  '--recursive', zarrpath, awspath]
    aws_command = ['aws', 's3', '--profile', aws_cli_profile, 'cp',  '--recursive', zarrpath, awspath]
  
    result = subprocess.run(aws_command, stderr=subprocess.PIPE)

     # Check if the command was successful
    if result.returncode == 0:
        return True, "" # Return True for success and None for error detail
    else:
    # If there was an error, return False and the error details
        error_detail = result.stderr.decode('utf-8') if result.stderr else "Unknown error"
        return False, error_detail

# Read the inputlist.csv using pandas
df = pd.read_csv(inputlist, dtype={'filename': str, 'secnum': str, 'transferflag': str, 'uploadflag': str})

# Traverse filename in upload path
for index, row in df.iterrows():
  filename = row['filename']
  section = (row['secnum'])
  transferflag = row['transferflag']
  uploadflag = row['uploadflag']
  
  # Define the path to the zarr file
  if isinstance(filename, str):
      zarr_path = os.path.join(upload_path, filename.replace('.czi', '.zarr'))
      zarr_file = os.path.basename(zarr_path)

      # Check if the file exists, the upload flag is f
      if uploadflag == '0' and transferflag == '1' and section != '-' and os.path.exists(zarr_path):
        try:
          # Upload the file to the S3 bucket
          success, error_detail = upload_to_s3(zarr_file, section)

          if not success:
            raise Exception(f"Error uploading file {filename} section {section} : {error_detail}")
          else:  
            print(f"Uploaded file {filename} section {section} to S3 bucket {s3_bucket}.")
            # Update the upload flag to 1
            df.at[index, 'uploadflag'] = '1'
            df.to_csv(inputlist, index=False)
        except Exception as e:
            print(f"Error uploading file {filename}: {e}")
            # Update the upload flag to 'e'
            df.at[index, 'uploadflag'] = 'e'

      # Write the updated DataFrame back to the input CSV file    
      df.to_csv(inputlist, index=False)

print(f"Updated inputlist CSV file written to {inputlist}.")
