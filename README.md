# GLOBAL WARM WING
!(readme_imgs/tyl.gif)
If only the Wright brothers could see us flying giant tylenols in the sky filled with people!

Airplanes need thick air to fly. Pilots love cold weather because it makes takeoff a breeze due to the denser air. Airlines hate hot weather and high altitudes because it means the planes can't be absolutely stuffed with revenue. This is because of thinner air.

Air density has a huge role to play in aviation. As global warming continues to reach into Hollywood-esque consequences, it is causing air density to thin out, which will require lightening loads or even total grounding of a flight. Takeoff is by far the strictest part of airplane weight.

How big of a problem is this? That is what this project attempts to detail.

# The main thought process
The primary method is to figure out where an airplane model (an "airframe") can take off given a runway's length, and air density. The dry air density is a trivial equation coming from a locations elevation and given temperature. From here, we simply witness and plot which airframes could take off at many airports from around the world, and start plugging in degrees of warming scenarios which may take many airports off of the ability list.

It is planned to be able to scrape thousands of global runways for various data, as well as some method of accurate global warming scenario at those runways. Currently there are 9 specific airframes which encompasses the widest possible variety while capturing the majority of passenger air travel.

# The complication
The major complication is an FAA standard called "ISA". Although the graphs of aircraft takeoff performance are easily found by googling "Aircraft characteristics for airport planning and maintenance for <airframe>," the data comes in a format which needs to be _unpacked_ into a more useful format.

ISA is a graph which plots the amount of weight you can add to a plane vs its runway length requirement (Airbus swaps the x-y axis making it "funner" to work with). Since this project only deals with 100% MTOW (max take-off weight), only MTOW data points can be used to recreate an aiframes take-off characteristics vs air density. The other pinch point is that the ISA graphs list altitudes as separate lines (separated by 2000 ft of elevation), and each line of elevation has its own "standard temperature." 

Here is what they are:
elev (1k ft):   |   standard temp (C)
0                   15
2                   11.04
4                    7.08
6                    3.12
8                   -0.84

To make matters worse, there is also an ISA+15 chart which lists the same as above but with the standard temps having +15 C to them. 

# Unpacking ISA
So how to unpack ISA? We find the given air density for that specific combination of elevation and standard temperature. Once we have this we can create a new plot (for each airframe) from scratch with labels: y=100% MTOW takeoff runway length required, and x=air density (kg/m^3). The 100% MTOW y value from the ISA graph becomes the new graph's y value. It's corresponding x value comes from that instance of ISA's air density.

For example: 
[]
reference:
https://www.desmos.com/calculator/hqckxhijut
The 100% MTOW of an Airbus a330-200 is 242 thousand kg. It has a data point for the 2000 ft. altitude line that on the ISA chart (Airbus has x-y axes flipped remember) which corresponds to 3283 meters of runway requirement. That is the new graph's y value. It's x value is whatever air density that ISA combination is, which is air_density(2000 ft. converted to meters, 11.04 celcius) => 1.1549 kg/m^3.

new graph: 
https://www.desmos.com/calculator/iuttzfxgla

# Complication number 2
Notice on the first desmos graph that many elevation's data points come nowhere close to the 100% MTOW. This is a problem due to a lack of enough data points. There is a provided script called mtow_fit/ln_e_fit.py which given a set of data points will curve fit to -a*ln(b - x) + c with a, b, and c being coefficients. It fits incredibly well. The purpose is only to get a single data point at the 100% MTOW so we can plot one more point on the new graph.

# New graph = Takeoff Characteristics
The new graph describes how much runway length is required given air density. The densest air on earth is about 1.6 kg/m^3 (-65 C in the arctic) so you can't travel too far to the right on the graph. As you travel to the left and delete air density it exponentially requires longer lengths until it becomes infinite. Imagine a plane in a vacuum, even a runway the length of Africa could not allow it to take off (some blessed rains might, however). The longest runway on earth (for commercial passenger traffic) is in China at 5500 meters length (which is 5x the length of the Clark building to Smith Engineering!).

This graph has a derivation which is more grounded from first principles of flying:
S(rho) = -(C1/rho) * ln(1 - (C2/rho))
where S is runway length,
C1 and C2 are coefficients.
Derivation available @ Dustins office (probably buried under 5 stacks of papers).
Typically these exact coefficients are _trade secrets_ by the manufacturers (exact wing area, coefficient of lift, etc). We need only to estimate it with.....

ANOTHER curve fit!

# Automating?
Yeah I don't feel like automating this. What are undergrads for, after all?
Exact way to do this for each airframe in "procedure to add new airframe.txt"

# Plotting
Finally once we have the coefficients for all airframes we are able to run data through it.

---

was last doing:
waiting for Dustin to:
invert that formula or give me the okay for estimation

--

score with MSE then graph the resulting coeffs in desmos to prove it is good
finally, write that down somewhere full formula
unpack ISA using it


# Planned airframes:
Airbus
a330-200
a320-neo
a380-800
a350-900

Boeing
737-800
777-300ER
787-9
747-400

CRJ (Canadair Regional Jet)
700

---


desmos code
{a}\ln\left({k}+x\right)+{o}
a amplitude
k hoz offset
o vert offset

then for each

I am going to figure out the chart by figuring out the ISA and altitude, plugging that into a formula


----
curve fitter did remarkably well!
the ln got close to what I got:
claude torch:
y = -0.997666955 * ln(260.4542166 - x) + 5.790600542
vs mine:
y = -1.056 ln(262-x) + 6.05
wow!
anyways the e^ curve did a lot better for all of these.