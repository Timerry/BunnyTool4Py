
import sys

if sys.version_info[0] != 2:
  raise Exception("Blockly build only compatible with Python 2.x.\nYou are using: " + sys.version)

import errno, glob, fnmatch, httplib, json, os, re, subprocess, threading, urllib


def import_path(fullpath):
  """Import a file with full path specification.
  Allows one to import from any directory, something __import__ does not do.

  Args:
      fullpath:  Path and filename of import.

  Returns:
      An imported module.
  """
  path, filename = os.path.split(fullpath)
  filename, ext = os.path.splitext(filename)
  sys.path.append(path)
  module = __import__(filename)
  reload(module)  # Might be out of date.
  del sys.path[-1]
  return module


HEADER = ("// Do not edit this file; automatically generated by build.py.\n'use strict';\n")

class Gen_compressed(threading.Thread):

  def __init__(self, search_paths):
    threading.Thread.__init__(self)
    self.search_paths = search_paths

  def run(self):
    self.gen_blocks("arduino")
    self.gen_generator("arduino")

  def gen_blocks(self, language):
    target_filename = language + "_blocks_compressed.js"
    # Define the parameters for the POST request.
    params = [
        ("compilation_level", "SIMPLE_OPTIMIZATIONS"),
        ("output_format", "json"),
        ("output_info", "compiled_code"),
        ("output_info", "warnings"),
        ("output_info", "errors"),
        ("output_info", "statistics"),
      ]

    # Read in all the source files.
    # Add Blockly.Blocks to be compatible with the compiler.
    params.append(("js_code", "goog.provide('Blockly.Blocks');"))
    params.append(("js_code", "goog.provide('Blockly.Types');"))
    filenames = []
    for root, folders, files in os.walk("blocks"):
        for filename in fnmatch.filter(files, "*.js"):
            filenames.append(os.path.join(root, filename))
    for filename in filenames:
      f = open(filename)
      params.append(("js_code", "".join(f.readlines())))
      f.close()

    # Remove Blockly.Blocks to be compatible with Blockly.
    remove = ["var Blockly={Blocks:{}};", "Blockly.Types={};"]
    self.do_compile(params, target_filename, filenames, remove)

  def gen_generator(self, language):
    target_filename = language + "_generator_compressed.js"
    # Define the parameters for the POST request.
    params = [
        ("compilation_level", "SIMPLE_OPTIMIZATIONS"),
        ("output_format", "json"),
        ("output_info", "compiled_code"),
        ("output_info", "warnings"),
        ("output_info", "errors"),
        ("output_info", "statistics"),
      ]

    # Read in all the source files.
    # Add Blockly.Generator to be compatible with the compiler.
    params.append(("js_code", "goog.provide('Blockly.Generator');"))
    params.append(("js_code", "goog.provide('Blockly.StaticTyping');"))
    filenames = glob.glob(
        os.path.join("generators", language, "*.js"))
    filenames.insert(0, os.path.join("generators", language + ".js"))
    for filename in filenames:
      f = open(filename)
      params.append(("js_code", "".join(f.readlines())))
      f.close()
    filenames.insert(0, "[goog.provide]")

    # Remove Blockly.Generator to be compatible with Blockly.
    remove = ["var Blockly={Generator:{}};", "Blockly.StaticTyping={};"]
    self.do_compile(params, target_filename, filenames, remove)

  def do_compile(self, params, target_filename, filenames, remove):
    # Send the request to Google.
    headers = {"Content-type": "application/x-www-form-urlencoded"}
    conn = httplib.HTTPSConnection("closure-compiler.appspot.com")
    conn.request("POST", "/compile", urllib.urlencode(params), headers)
    response = conn.getresponse()
    json_str = response.read()
    conn.close()

    # Parse the JSON response.
    json_data = json.loads(json_str)

    def file_lookup(name):
      if not name.startswith("Input_"):
        return "???"
      n = int(name[6:]) - 1
      return filenames[n]

    if json_data.has_key("serverErrors"):
      errors = json_data["serverErrors"]
      for error in errors:
        print("SERVER ERROR: %s" % target_filename)
        print(error["error"])
    elif json_data.has_key("errors"):
      errors = json_data["errors"]
      for error in errors:
        print("FATAL ERROR")
        print(error["error"])
        if error["file"]:
          print("%s at line %d:" % (
              file_lookup(error["file"]), error["lineno"]))
          print(error["line"])
          print((" " * error["charno"]) + "^")
        sys.exit(1)
    else:
      if json_data.has_key("warnings"):
        warnings = json_data["warnings"]
        for warning in warnings:
          print("WARNING")
          print(warning["warning"])
          if warning["file"]:
            print("%s at line %d:" % (
                file_lookup(warning["file"]), warning["lineno"]))
            print(warning["line"])
            print((" " * warning["charno"]) + "^")
        print()

      if not json_data.has_key("compiledCode"):
        print("FATAL ERROR: Compiler did not return compiledCode.")
        sys.exit(1)

      code = HEADER + "\n" + json_data["compiledCode"]
      for code_statement in remove:
          code = code.replace(code_statement, "")

      # Trim down Google's Apache licences.
      # The Closure Compiler used to preserve these until August 2015.
      # Delete this in a few months if the licences don't return.
      LICENSE = re.compile("""/\\*

 [\w ]+

 (Copyright \\d+ Google Inc.)
 https://developers.google.com/blockly/

 Licensed under the Apache License, Version 2.0 \(the "License"\);
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
\\*/""")
      code = re.sub(LICENSE, r"\n// \1  Apache License 2.0", code)

      stats = json_data["statistics"]
      original_b = stats["originalSize"]
      compressed_b = stats["compressedSize"]
      if original_b > 0 and compressed_b > 0:
        f = open(target_filename, "w")
        f.write(code)
        f.close()

        original_kb = int(original_b / 1024 + 0.5)
        compressed_kb = int(compressed_b / 1024 + 0.5)
        ratio = int(float(compressed_b) / float(original_b) * 100 + 0.5)
        print("SUCCESS: " + target_filename)
        print("Size changed from %d KB to %d KB (%d%%)." % (
            original_kb, compressed_kb, ratio))
      else:
        print("UNKNOWN ERROR")


class Gen_langfiles(threading.Thread):
  """Generate JavaScript file for each natural language supported.

  Runs in a separate thread.
  """

  def __init__(self):
    threading.Thread.__init__(self)

  def _rebuild(self, srcs, dests):
    # Determine whether any of the files in srcs is newer than any in dests.
    try:
      return (max(os.path.getmtime(src) for src in srcs) > min(os.path.getmtime(dest) for dest in dests))
    except OSError as e:
      # Was a file not found?
      if e.errno == errno.ENOENT:
        # If it was a source file, we can't proceed.
        if e.filename in srcs:
          print("Source file missing: " + e.filename)
          sys.exit(1)
        else:
          # If a destination file was missing, rebuild.
          return True
      else:
        print("Error checking file creation times: " + e)

  def generate_blockly(self):
    # The files msg/json/{en,qqq,synonyms}.json depend on msg/messages.js.
    if self._rebuild([os.path.join("msg", "messages.js")], [os.path.join("msg", "json", f) for f in ["en.json", "qqq.json", "synonyms.json"]]):
      try:
        subprocess.check_call([
            "python",
            os.path.join("i18n", "js_to_json.py"),
            "--input_file", "msg/messages.js",
            "--output_dir", "msg/json/",
            "--quiet"])
      except (subprocess.CalledProcessError, OSError) as e:
        # Documentation for subprocess.check_call says that CalledProcessError
        # will be raised on failure, but I found that OSError is also possible.
        print("Error running i18n/js_to_json.py: ", e)
        sys.exit(1)

    # Checking whether it is necessary to rebuild the js files would be a lot of
    # work since we would have to compare each <lang>.json file with each
    # <lang>.js file.  Rebuilding is easy and cheap, so just go ahead and do it.
    try:
      # Use create_messages.py to create .js files from .json files.
      cmd = [
          "python",
          os.path.join("i18n", "create_messages.py"),
          "--source_lang_file", os.path.join("msg", "json", "en.json"),
          "--source_synonym_file", os.path.join("msg", "json", "synonyms.json"),
          "--key_file", os.path.join("msg", "json", "keys.json"),
          "--output_dir", os.path.join("msg", "js"),
          "--quiet"]
      json_files = glob.glob(os.path.join("msg", "json", "*.json"))
      json_files = [file for file in json_files if not (file.endswith(("keys.json", "synonyms.json", "qqq.json", "_ardublockly.json")))]
      cmd.extend(json_files)
      subprocess.check_call(cmd)
    except (subprocess.CalledProcessError, OSError) as e:
      print("Error running i18n/create_messages.py: ", e)
      sys.exit(1)

    # Output list of .js files created.
    for f in json_files:
      # This assumes the path to the current directory does not contain "json".
      f = f.replace("json", "js")
      if os.path.isfile(f):
        print("SUCCESS: " + f)
      else:
        print("FAILED to create " + f)

  def run(self):
    self.generate_blockly()


if __name__ == "__main__":
  try:
    calcdeps = import_path(os.path.join(os.path.pardir, "closure-library", "closure", "bin", "calcdeps.py"))
  except ImportError:
    if os.path.isdir(os.path.join(os.path.pardir, "closure-library-read-only")):
      # Dir got renamed when Closure moved from Google Code to GitHub in 2014.
      print("Error: Closure directory needs to be renamed from"
            "'closure-library-read-only' to 'closure-library'.\n"
            "Please rename this directory.")
    elif os.path.isdir(os.path.join(os.path.pardir, "google-closure-library")):
      # When Closure is installed by npm, it is named "google-closure-library".
      #calcdeps = import_path(os.path.join(
      # os.path.pardir, "google-closure-library", "closure", "bin", "calcdeps.py"))
      print("Error: Closure directory needs to be renamed from"
           "'google-closure-library' to 'closure-library'.\n"
           "Please rename this directory.")
    else:
      print("""Error: Closure not found.  Read this:
https://developers.google.com/blockly/hacking/closure""")
    sys.exit(1)

  search_paths = calcdeps.ExpandDirectories(["core", os.path.join(os.path.pardir, "closure-library")])

  Gen_compressed(search_paths).start()
  Gen_langfiles().start()
