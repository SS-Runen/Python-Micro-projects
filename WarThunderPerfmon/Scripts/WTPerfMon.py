import os
import datetime as dt
import pprint
from pathlib import Path


def parse_line(string:str):
    lst_column = []
    
    string = string.rstrip()
    
    event_code = (string.split(' ')[0]).rstrip()
    lst_column.append(event_code)
    string = string.replace(event_code, "", 1)

    halves = string.split('@')
    if '@' in string and (len(halves) == 2):
        lst_column.append(halves[0].rstrip())
        lst_column.append(halves[1].rstrip())
    else:
        lst_column.append(string)

    # print(lst_column)
    return lst_column


def parse_textfile(input_filepath):    
    file_obj = open(input_filepath, 'r')
    lst_lines = file_obj.readlines()
    file_obj.close()

    lst_cleanlines = []

    for row_index in range(len(lst_lines)):
        if not lst_lines[row_index].isspace() and (len(lst_lines[row_index]) >= 1):
            lst_cleanlines.append(lst_lines[row_index])
    
    del lst_lines

    for row_index in range(len(lst_cleanlines)):
        lst_columns = parse_line(lst_cleanlines[row_index])
        lst_cleanlines[row_index] = ','.join(lst_columns)    
    
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
    # lst_infile_paths = [str(filepath) for filepath in input_filepath.glob("%s*.txt" % filename_prefix)]    

    str_timestamp = str(dt.datetime.now()).replace(':', '.') + ' '
    if (outfolder_path / outfile_name).exists and (overwrite_outfiles is False):
        outfile_name = str_timestamp + outfile_name
        fileobj = open(file=(outfolder_path / outfile_name), mode='x')
    else:
        fileobj = open(file=(outfolder_path / outfile_name), mode='w')
                
    fileobj.writelines(["Event,Vehicle,Distance", ""])
    fileobj.close()

    for absolute_path in lst_infile_paths:
        lst_records = parse_textfile(absolute_path)                
        fileobj = open(file=(outfolder_path / outfile_name), mode='a')        

        for line in lst_records:            
            fileobj.write(line + '\n')
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
