import json
import toml

# Read Pipfile.lock
with open('Pipfile.lock') as f:
    lock_data = json.load(f)

# Read Pipfile
with open('Pipfile') as f:
    pipfile_data = toml.load(f)

# Update versions in Pipfile data
for section in ['default', 'develop']:
    if section in lock_data:
        for package, info in lock_data[section].items():
            if package in pipfile_data['packages']:
                pipfile_data['packages'][package] = f"=={info['version']}"
            elif section == 'develop' and package in pipfile_data.get('dev-packages', {}):
                pipfile_data['dev-packages'][package] = f"=={info['version']}"

# Write updated Pipfile
with open('Pipfile', 'w') as f:
    toml.dump(pipfile_data, f)

print("Pipfile updated with exact versions from Pipfile.lock")