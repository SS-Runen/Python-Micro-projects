import os
import datetime as dt
import pprint
import re
from pathlib import Path


def parse_textfile(input_filepath):    
    file_obj = open(input_filepath, 'r')
    lst_lines = file_obj.readlines()
    file_obj.close()

    lst_cleanlines = []
    vehicle_used = str(input_filepath).split(r'\''.strip("'"))[-1]
    vehicle_used = vehicle_used.strip(".txt")
    vehicle_used = re.sub("temp kd", "", vehicle_used, flags=re.I)

    date_recorded = "N.A."
    for row_index in range(len(lst_lines)):
        current_line = lst_lines[row_index].replace(',', '&').split('@')
        current_line = [n.strip() for n in current_line]
        if len(current_line) == 1:
            if re.search(r"\d{4}[\-_/](\d{1,2}[\-_/]\d{1,2})", current_line[0]) is not None:
                date_recorded = current_line[0]
                continue
        elif len(current_line) > 1:
            del current_line[0]
            current_line = [date_recorded, vehicle_used] + current_line
            lst_cleanlines.append(','.join(current_line))
        else:
            continue
    
    # pprint.pprint(lst_cleanlines)
    return lst_cleanlines


def txt_to_csv(
    input_filepath = Path(r"../InputFiles/"),
    outfile_name = "records.csv",
    outfolder_path = Path(r"../OutputFiles/"),
    filename_prefix = "Temp KD",
    print_logfile_entry = True,
    overwrite_outfiles = False
    ):

    try:
        script_path = Path(os.path.abspath(__file__)).parent
        os.chdir((script_path))
        print(f"Set current directory to script location:\n{script_path}")
    except Exception as e:
        print(
            """Failed to change current working directory to the folder containing this script.
            \nThis could be because you are not using a Windows or Unix operating system. Error:\n*****
            """)
        print(e)

    str_logfile_path = "scripts_logfile.txt"    

    if not outfolder_path.exists():
        os.mkdir(str(outfolder_path))

    lst_infile_paths = [Path(filepath).absolute() for filepath in input_filepath.glob(f"{filename_prefix}*.txt")]

    str_timestamp = str(dt.datetime.now()).replace(':', '.') + ' '
    fileobj = None
    if (outfolder_path / outfile_name).exists and (overwrite_outfiles is False):
        outfile_name = str_timestamp + outfile_name
        fileobj = open(file=(outfolder_path / outfile_name), mode='x')
    else:
        fileobj = open(file=(outfolder_path / outfile_name), mode='w')
                
    fileobj.write("DateRecorded, VehicleUsed, Event, EnemyVehicle, Distance, OrientationInSight, EnemySpeed, SelfSpeed\n")
    fileobj.close()

    for absolute_path in lst_infile_paths:
        lst_records = parse_textfile(absolute_path)                
        fileobj = open(file=(outfolder_path / outfile_name), mode='a')        

        for line in lst_records:            
            fileobj.write(line + "\n")
        fileobj.close()
    
    if Path(str_logfile_path).exists():
        logfile = open(str_logfile_path, 'a')
    else:
        logfile = open(str_logfile_path, 'x')
    
    str_log = "\n****\n" + str(dt.datetime.now()) + '\n'
    str_log += f"\nInput Files at:\n {input_filepath.resolve()}"
    str_log += f"\nOutput Folder at:\n {outfolder_path.resolve()}"
    str_log += "\nProcessed the following files:\n"
    str_log += pprint.pformat(lst_infile_paths)
    str_log += "\n====\n"

    logfile.write(str_log)
    if print_logfile_entry:
        print(str_log)

    return None


def main():
    txt_to_csv(overwrite_outfiles=True)
    # txt_to_csv(
    #     filename_prefix="Temp KD Centurion Mk. 10",
    #     outfile_name="records_centmk10.csv"
    # )
    return None


if __name__ == "__main__":
    main()
