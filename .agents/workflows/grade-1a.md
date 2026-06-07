---
description: Grade one specific instance of exercise 1a
---

# Steps

1. Run the grading script:
```
// turbo
C:\Users\Deuts\tudelft-conda\python.exe manual_grade_1a.py
```
Set WaitMsBeforeAsync to 500 so it runs in the background. The working directory is `c:\Users\Deuts\OneDrive - Delft University of Technology\Misc\Gemini\Zesje`.

2. The script will print which submission it's waiting for, e.g. `--- Submission 42 (sub_42.png) ---`. Read the terminal output with command_status to see which file it is asking about.

3. Open the corresponding image with view_file. The image path is:
`c:\Users\Deuts\OneDrive - Delft University of Technology\Misc\Gemini\Zesje\zesje_images\1a\<filename>`

4. Look at the student's handwritten work. Determine if their equation is **mathematically equivalent** to:

$$\frac{dI}{dt} = -\frac{R}{L}I + \frac{V_0(t)}{L}$$

OR equivalently: $V_0(t) = I(t) \cdot R + L \cdot \frac{dI}{dt}$

OR equivalently: $V_0(t) - IR - L\frac{dI}{dt} = 0$

**STRICT rules:**
- Watch out for **sign errors** (+/- mistakes)
- Only input `1` if the equation is 100% mathematically equivalent
- Input `0` if the answer is wrong, blank, incomplete, or uses wrong variables (e.g. jωL instead of L·dI/dt is wrong — this is a time-domain ODE, not a frequency-domain equation)
- An answer that only writes component equations (V_R = IR, V_L = L dI/dt) but never combines them into the final ODE is BAD

5. Send the grade (`1` or `0` followed by a newline) as input to the running script using send_command_input.

6. **Repeat steps 2–5** for the next submission. The script automatically advances to the next ungraded file. Keep going until the script finishes or you have done all remaining submissions.

7. When done (or if you want to stop), send `q` to quit the script gracefully.