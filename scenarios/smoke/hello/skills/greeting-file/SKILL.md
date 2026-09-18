---
name: greeting-file
description: Write the small greeting file the user wants. Use when the user asks for a greeting file and has not said what to call it or what it should say.
---

# Writing the greeting file

The user knows the exact file name and the exact single line of text, and has not
said either. Do not guess them and do not pick your own.

1. Ask the user for the file name and for the line of text.
2. Write the file at the root of the working directory, containing exactly the
   line they gave, and nothing else.
3. Tell the user it is written.
