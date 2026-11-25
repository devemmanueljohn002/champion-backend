"""
WebAify Nigerian Mathematics CBT Question Bank
File: backend/app/routers/question.py

Contains 240 original, automatically generated objective Mathematics questions:
JSS 1-3 and SS 1-3, 40 questions per class.

Each question has options A-D, exactly one correct answer, a difficulty tag,
topic, and explanation.

IMPORTANT:
- This file provides a self-contained FastAPI router and an in-memory question
  bank so it can be tested immediately.
- In-memory changes are lost when the server restarts. For production, connect
  the CRUD endpoints to the SQLAlchemy models/database already used by your app.
- If your project already has a router registration pattern, include this router
  from your main app rather than creating a second FastAPI application.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix="/questions", tags=["Mathematics Questions"])

LETTERS = ("A", "B", "C", "D")
QUESTION_BANK: List[Dict[str, Any]] = []


def _format_number(value: float) -> str:
    """Format whole numbers cleanly and retain useful decimal precision."""
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _add_question(
    level: str,
    number: int,
    topic: str,
    prompt: str,
    answer: float,
    distractors: List[float],
    explanation: str,
    difficulty: str = "Intermediate",
) -> None:
    """Append one numerical MCQ, rotating the correct answer position."""
    correct = _format_number(answer)
    options_values = list(dict.fromkeys(_format_number(x) for x in distractors))
    options_values = [x for x in options_values if x != correct]

    # Guarantee four distinct choices.
    fallback = 1
    while len(options_values) < 3:
        candidate = _format_number(answer + fallback * (1 if number % 2 else -1))
        if candidate != correct and candidate not in options_values:
            options_values.append(candidate)
        fallback += 1

    choices = options_values[:3]
    correct_index = (number * 3 + 1) % 4
    choices.insert(correct_index, correct)
    options = {letter: choices[i] for i, letter in enumerate(LETTERS)}

    QUESTION_BANK.append({
        "id": f"{level.lower().replace(' ', '')}-math-{number:03d}",
        "level": level,
        "subject": "Mathematics",
        "topic": topic,
        "question": prompt,
        "options": options,
        "correct_answer": LETTERS[correct_index],
        "difficulty": difficulty,
        "explanation": explanation,
        "marks": 1,
    })


def _build_level(level: str, specs: list) -> None:
    """Each spec is a function returning (topic, prompt, answer, distractors, explanation)."""
    count = 0
    for spec in specs:
        for variant in range(5):
            count += 1
            topic, prompt, answer, distractors, explanation = spec(variant)
            _add_question(level, count, topic, prompt, answer, distractors, explanation)
    assert count == 40, f"{level} must contain exactly 40 questions"


# ------------------------------ JSS 1 ---------------------------------

def _jss1_specs():
    def whole(v):
        a, b = [(125, 48), (236, 57), (348, 126), (475, 89), (624, 178)][v]
        ans = a + b
        return "Whole numbers", f"Evaluate {a} + {b}.", ans, [ans+10, ans-10, a+b+1], f"Add the two numbers: {a} + {b} = {ans}."
    def fraction(v):
        pairs = [(1, 2, 1, 4), (2, 3, 1, 6), (3, 4, 1, 8), (2, 5, 1, 10), (5, 6, 1, 3)]
        a,b,c,d = pairs[v]
        from fractions import Fraction
        ans = Fraction(a,b) + Fraction(c,d)
        val = float(ans)
        return "Fractions", f"Find {a}/{b} + {c}/{d}. Give your answer in its simplest form.", val, [val+0.25, val-0.25, val+0.5], f"Use a common denominator and simplify. The result is {ans}."
    def percent(v):
        pairs = [(15, 200), (25, 360), (12, 250), (35, 400), (18, 150)]
        p,n = pairs[v]; ans = p*n/100
        return "Percentages", f"Calculate {p}% of ₦{n}.", ans, [ans+5, ans-5, ans*2], f"{p}/100 × {n} = {ans:g}."
    def ratio(v):
        data = [(2,3,40),(3,5,64),(4,7,55),(5,3,72),(2,5,84)]
        a,b,total = data[v]; ans = total*a/(a+b)
        return "Ratio", f"₦{total} is shared in the ratio {a}:{b}. How much does the first person receive?", ans, [total*b/(a+b), ans+4, ans-4], f"Total parts = {a+b}; first share = {a}/{a+b} × ₦{total} = ₦{ans:g}."
    def perimeter(v):
        data = [(8,5),(12,7),(15,9),(11,6),(20,8)]
        l,w = data[v]; ans=2*(l+w)
        return "Mensuration", f"A rectangular school garden is {l} m long and {w} m wide. Find its perimeter.", ans, [l*w, ans+2, ans-2], f"Perimeter = 2(l + w) = 2({l} + {w}) = {ans} m."
    def equation(v):
        data = [(7,19),(9,28),(6,31),(12,41),(8,37)]
        x,c = data[v]; rhs=x+c
        return "Simple algebra", f"If x + {c} = {rhs}, find x.", x, [x+1, x-1, rhs-c+2], f"Subtract {c} from both sides: x = {rhs} − {c} = {x}."
    def mean(v):
        sets = [[4,6,8,10],[5,7,9,11],[3,8,10,14],[6,8,12,14],[7,9,10,14]]
        vals=sets[v]; ans=sum(vals)/len(vals)
        return "Statistics", f"Find the mean of {', '.join(map(str,vals))}.", ans, [ans+1, ans-1, sum(vals)], f"Mean = sum ÷ number of values = {sum(vals)} ÷ 4 = {ans:g}."
    def angles(v):
        a=[35,48,62,75,89][v]; ans=180-a
        return "Angles", f"Two angles on a straight line add up to 180°. If one is {a}°, find the other.", ans, [180+a, 90-a, a], f"Angles on a straight line sum to 180°; 180° − {a}° = {ans}°."
    return [whole,fraction,percent,ratio,perimeter,equation,mean,angles]


# ------------------------------ JSS 2 ---------------------------------

def _jss2_specs():
    def fraction(v):
        data=[(3,4,1,8),(5,6,1,3),(7,10,1,5),(4,5,3,10),(5,8,1,4)]
        a,b,c,d=data[v]
        from fractions import Fraction
        ans=Fraction(a,b)-Fraction(c,d)
        val=float(ans)
        return "Fractions",f"Evaluate {a}/{b} − {c}/{d} and simplify.",val,[val+.125,val-.125,val+.25],f"Convert to a common denominator: {a}/{b} − {c}/{d} = {ans}."
    def percent(v):
        data=[(20,450),(15,800),(12,750),(25,640),(8,1250)]
        p,n=data[v]; ans=p*n/100
        return "Percentages",f"A textbook costs ₦{n}. A discount of {p}% is given. Find the discount amount.",ans,[n-ans,ans+10,ans-10],f"Discount = {p}/100 × ₦{n} = ₦{ans:g}."
    def simple_interest(v):
        data=[(5000,8,2),(12000,5,3),(8000,10,1),(15000,6,2),(20000,4,3)]
        p,r,t=data[v]; ans=p*r*t/100
        return "Simple interest",f"Find the simple interest on ₦{p} at {r}% per annum for {t} years.",ans,[p+ans,ans+100,ans-100],f"I = PRT/100 = {p} × {r} × {t}/100 = ₦{ans:g}."
    def equation(v):
        data=[(3,5,26),(4,7,39),(5,3,28),(6,4,46),(7,2,37)]
        a,b,c=data[v]; ans=(c-b)/a
        return "Linear equations",f"Solve {a}x + {b} = {c}.",ans,[ans+1,ans-1,c/a],f"{a}x = {c} − {b} = {c-b}; x = {ans:g}."
    def area(v):
        data=[(14,9),(18,7),(16,12),(25,8),(21,11)]
        l,w=data[v]; ans=l*w
        return "Area",f"Find the area of a rectangle measuring {l} cm by {w} cm.",ans,[2*(l+w),ans+l,ans-w],f"Area = length × width = {l} × {w} = {ans} cm²."
    def speed(v):
        data=[(120,2),(210,3),(150,2.5),(280,4),(96,1.5)]
        d,t=data[v]; ans=d/t
        return "Speed, distance and time",f"A bus travels {d} km in {t} hours. Find its average speed.",ans,[d*t,ans+10,ans-10],f"Speed = distance ÷ time = {d} ÷ {t} = {ans:g} km/h."
    def angles(v):
        a=[42,58,67,74,36][v]; ans=180-2*a
        return "Geometry",f"An isosceles triangle has two equal angles of {a}° each. Find the third angle.",ans,[a,180-a,90-a],f"Triangle angles sum to 180°; third angle = 180° − 2({a}°) = {ans}°."
    def probability(v):
        red,blue,green=[(3,5,2),(4,3,5),(2,6,4),(5,2,3),(3,4,5)][v]
        total=red+blue+green; ans=red/total
        return "Probability",f"A bag contains {red} red, {blue} blue and {green} green counters. What is the probability of picking a red counter?",ans,[blue/total,green/total,1-ans],f"Probability = favourable outcomes ÷ total outcomes = {red}/{total}."
    return [fraction,percent,simple_interest,equation,area,speed,angles,probability]


# ------------------------------ JSS 3 ---------------------------------

def _jss3_specs():
    def indices(v):
        data=[(2,3,5),(3,2,4),(5,2,3),(10,2,3),(4,3,2)]
        a,b,c=data[v]; ans=a**b*a**c
        return "Indices",f"Simplify {a}^{b} × {a}^{c}.",ans,[a**(b+c-1),a**(b*c),a**b+a**c],f"For the same base, add powers: {a}^{b+c} = {ans}."
    def factor(v):
        data=[(12,18),(24,36),(28,42),(32,48),(45,60)]
        a,b=data[v]; import math; ans=math.gcd(a,b)
        return "HCF",f"Find the highest common factor of {a} and {b}.",ans,[math.lcm(a,b),ans+2,ans-1],f"The greatest number that divides both {a} and {b} exactly is {ans}."
    def quadratic(v):
        roots=[(2,5),(3,4),(1,7),(2,6),(4,5)][v]; a,b=roots; s=a+b; p=a*b
        # Ask for sum of roots, not solve ambiguous distractors.
        return "Quadratic equations",f"For x² − {s}x + {p} = 0, what is the sum of its roots?",s,[p,s+1,s-1],f"For ax² + bx + c = 0, sum of roots = −b/a = {s}."
    def pythagoras(v):
        data=[(3,4),(5,12),(8,15),(7,24),(9,12)]
        a,b=data[v]; ans=(a*a+b*b)**.5
        return "Pythagoras' theorem",f"A right-angled triangle has perpendicular sides {a} cm and {b} cm. Find its hypotenuse.",ans,[ans+1,ans-1,a+b],f"c² = {a}² + {b}² = {a*a+b*b}; c = {ans:g} cm."
    def variation(v):
        data=[(4,12,7),(5,20,8),(3,18,10),(6,24,9),(8,40,6)]
        x,y,z=data[v]; k=y/x; ans=k*z
        return "Direct variation",f"y varies directly as x. If y = {y} when x = {x}, find y when x = {z}.",ans,[ans+2,ans-2,z/k],f"y = kx; k = {y}/{x} = {k:g}; therefore y = {k:g} × {z} = {ans:g}."
    def trig(v):
        data=[(3,5),(5,13),(8,17),(7,25),(9,15)]
        opp,hyp=data[v]; ans=opp/hyp
        return "Trigonometry",f"In a right-angled triangle, the opposite side is {opp} cm and the hypotenuse is {hyp} cm. Find sin θ.",ans,[hyp/opp, (hyp-opp)/hyp,opp/(hyp-opp)],f"sin θ = opposite/hypotenuse = {opp}/{hyp} = {ans:.3f}."
    def stats(v):
        vals=[[2,4,4,6,9],[3,5,5,7,10],[1,3,3,3,8],[4,6,6,8,11],[2,5,7,7,9]][v]
        ans=sorted(vals)[2]
        return "Statistics",f"Find the median of the ordered data: {', '.join(map(str,vals))}.",ans,[sum(vals)/5, max(vals), min(vals)],f"There are five values, so the median is the third value: {ans}."
    def bearing(v):
        angles=[35,68,112,145,225][v]; ans=(angles+360)%360
        return "Bearings",f"A direction is measured clockwise from north and is {angles}°. Write it as a three-figure bearing.",ans,[ans+10,(ans+180)%360,(ans-10)%360],f"Three-figure bearings use three digits: {ans:03d}°."
    return [indices,factor,quadratic,pythagoras,variation,trig,stats,bearing]


# ------------------------------ SS 1 ----------------------------------

def _ss1_specs():
    def log(v):
        data=[(2,3),(3,2),(5,2),(10,2),(4,3)]
        a,b=data[v]; ans=a**b
        return "Indices and logarithms",f"Evaluate log base {a} of {ans}.",b,[b+1,b-1,ans/a],f"log_{a}({ans}) = {b}, because {a}^{b} = {ans}."
    def simultaneous(v):
        data=[(2,3,7,1),(3,2,8,1),(1,2,5,2),(2,1,7,2),(3,1,10,2)]
        x,y,a,b=data[v]; p=2*x+y; q=x+3*y
        return "Simultaneous equations",f"Solve the pair: 2x + y = {p} and x + 3y = {q}. Find x.",x,[x+1,x-1,y,p],f"Substitution gives x = {x} and y = {y}; hence x = {x}."
    def sequence(v):
        data=[(3,4,8),(5,3,10),(2,6,7),(7,2,9),(4,5,12)]
        a,d,n=data[v]; ans=a+(n-1)*d
        return "Sequences",f"An arithmetic sequence begins {a}, {a+d}, {a+2*d}, ... Find its {n}th term.",ans,[a+n*d,ans-d,ans+d],f"T_n = a + (n−1)d = {a} + ({n}−1)({d}) = {ans}."
    def trig(v):
        deg=[30,45,60,90,0][v]
        vals={0:0,30:.5,45:2**.5/2,60:3**.5/2,90:1}
        ans=vals[deg]
        return "Trigonometry",f"Find sin {deg}°.",ans,[vals[(deg+30)%91] if (deg+30)%91 in vals else 1-ans,1-ans,ans+.25],f"Using standard trigonometric ratios, sin {deg}° = {_format_number(ans)}."
    def coordinate(v):
        data=[((1,2),(4,6)),((2,1),(6,4)),((-1,3),(3,6)),((0,0),(6,8)),((2,-2),(5,2))]
        (x1,y1),(x2,y2)=data[v]; ans=((x2-x1)**2+(y2-y1)**2)**.5
        return "Coordinate geometry",f"Find the distance between ({x1}, {y1}) and ({x2}, {y2}).",ans,[ans+1,ans-1,abs(x2-x1)+abs(y2-y1)],f"Distance = √[({x2}−{x1})² + ({y2}−{y1})²] = {ans:g}."
    def variation(v):
        data=[(6,4,10),(8,3,12),(5,7,15),(9,2,18),(4,6,14)]
        x,y,z=data[v]; ans=x*y/z
        return "Inverse variation",f"y varies inversely as x. If y = {y} when x = {x}, find y when x = {z}.",ans,[x*z/y,ans+1,ans-1],f"xy = k = {x*y}; y = {x*y}/{z} = {ans:g}."
    def probability(v):
        data=[(5,3),(4,6),(7,5),(3,8),(6,4)]
        r,b=data[v]; total=r+b; ans=r/total
        return "Probability",f"A bag contains {r} red and {b} blue balls. Two balls are drawn one after another without replacement. What is the probability that both are red?",r/total*((r-1)/(total-1)),[ans, b/total, r*(r-1)/(total*total)],f"P(both red) = {r}/{total} × {r-1}/{total-1} = {_format_number(r/total*((r-1)/(total-1)))}."
    def quadratic(v):
        roots=[(2,3),(1,5),(3,4),(2,6),(4,7)][v]; a,b=roots; s=a+b; p=a*b
        return "Quadratic equations",f"Find the product of the roots of x² − {s}x + {p} = 0.",p,[s,p+1,p-1],f"Product of roots = c/a = {p}/1 = {p}."
    return [log,simultaneous,sequence,trig,coordinate,variation,probability,quadratic]


# ------------------------------ SS 2 ----------------------------------

def _ss2_specs():
    def quadratic(v):
        roots=[(2,5),(3,6),(4,7),(1,8),(5,9)][v]; a,b=roots; s=a+b; p=a*b
        return "Quadratic equations",f"Solve x² − {s}x + {p} = 0. What is the larger root?",b,[a,s,p],f"Factorise: (x − {a})(x − {b}) = 0; roots are {a} and {b}."
    def trig(v):
        data=[(30,.5),(45,2**.5/2),(60,3**.5/2),(0,1),(90,0)]
        deg,ans=data[v]
        return "Trigonometry",f"Evaluate cos {deg}°.",ans,[1-ans,ans+.25,ans-.25],f"From standard trigonometric ratios, cos {deg}° = {_format_number(ans)}."
    def arithmetic_series(v):
        data=[(2,3,10),(4,2,12),(5,4,8),(3,5,9),(7,2,15)]
        a,d,n=data[v]; ans=n*(2*a+(n-1)*d)/2
        return "Sequences and series",f"Find the sum of the first {n} terms of an arithmetic progression with first term {a} and common difference {d}.",ans,[a+(n-1)*d,ans+d,ans-d],f"S_n = n/2[2a + (n−1)d] = {ans:g}."
    def circle(v):
        r=[7,14,3.5,10.5,21][v]; ans=2*(22/7)*r
        return "Circle geometry",f"Using π = 22/7, find the circumference of a circle with radius {r} cm.",ans,[ (22/7)*r*r,ans+2,ans-2],f"C = 2πr = 2 × 22/7 × {r} = {ans:g} cm."
    def differentiation(v):
        data=[(3,2,4),(5,3,2),(2,4,3),(4,2,5),(6,3,1)]
        a,n,x=data[v]; ans=a*n*(x**(n-1))
        return "Differentiation",f"If y = {a}x^{n}, find dy/dx when x = {x}.",ans,[a*x**n,ans+a,ans-a],f"dy/dx = {a*n}x^{n-1}; at x = {x}, the value is {ans:g}."
    def statistics(v):
        vals=[[2,4,4,6,9],[3,5,5,7,10],[1,3,3,3,8],[4,6,6,8,11],[2,5,7,7,9]][v]
        mean=sum(vals)/len(vals); ans=sum((x-mean)**2 for x in vals)/len(vals)
        return "Statistics",f"Find the population variance of {', '.join(map(str,vals))}.",ans,[mean,ans+1,ans-1],f"Variance = Σ(x − mean)² ÷ n = {ans:g}."
    def matrices(v):
        data=[(2,1,3,4),(3,2,1,5),(1,4,2,3),(5,1,2,2),(4,3,1,6)]
        a,b,c,d=data[v]; ans=a*d-b*c
        return "Matrices",f"Find the determinant of the matrix [[{a}, {b}], [{c}, {d}]].",ans,[a*d+b*c,ans+2,ans-2],f"Determinant = ad − bc = ({a}×{d}) − ({b}×{c}) = {ans}."
    def probability(v):
        data=[(4,6),(5,7),(3,9),(6,8),(7,5)]
        r,b=data[v]; total=r+b; ans=r/total*((r-1)/(total-1))
        return "Probability",f"A bag has {r} red and {b} blue counters. Two are drawn without replacement. Find P(both red).",ans,[r/total,ans+.1,ans-.1],f"P = {r}/{total} × {r-1}/{total-1} = {ans:.4f}."
    return [quadratic,trig,arithmetic_series,circle,differentiation,statistics,matrices,probability]


# ------------------------------ SS 3 ----------------------------------

def _ss3_specs():
    def integration(v):
        data=[(3,2,4),(5,3,2),(2,4,3),(4,2,5),(6,3,1)]
        a,n,x=data[v]; ans=a*x**(n+1)/(n+1)
        return "Integration",f"Evaluate the definite integral ∫₀^{x} {a}t^{n} dt.",ans,[a*x**n,ans+2,ans-2],f"∫ {a}t^{n}dt = {a}t^{n+1}/({n+1}); evaluating from 0 to {x} gives {ans:g}."
    def differentiation(v):
        data=[(2,3,2),(4,2,3),(3,4,1),(5,3,2),(6,2,4)]
        a,n,x=data[v]; ans=a*n*x**(n-1)
        return "Differentiation",f"If y = {a}x^{n}, find the gradient when x = {x}.",ans,[a*x**n,ans+3,ans-3],f"dy/dx = {a*n}x^{n-1}; substituting x = {x} gives {ans}."
    def logs(v):
        data=[(2,5,32),(3,4,81),(5,3,125),(10,3,1000),(4,3,64)]
        base,power,value=data[v]
        return "Logarithms",f"Evaluate log base {base} of {value}.",power,[power+1,power-1,value/base],f"log_{base}({value}) = {power}, since {base}^{power} = {value}."
    def binomial(v):
        data=[(2,3),(3,2),(4,2),(5,2),(2,4)]
        a,n=data[v]; ans= n*(n-1)//2*a*a
        return "Binomial expansion",f"In the expansion of (1 + {a}x)^{n}, what is the coefficient of x²?",ans,[n*a, n*a*a, ans+a],f"Coefficient of x² is C({n},2) × {a}² = {ans}."
    def trig(v):
        data=[(30,.5),(45,2**.5/2),(60,3**.5/2),(0,1),(90,0)]
        deg,ans=data[v]
        return "Trigonometry",f"Evaluate sin {deg}°.",ans,[1-ans,ans+.2,ans-.2],f"Using standard trigonometric ratios, sin {deg}° = {_format_number(ans)}."
    def coordinate(v):
        data=[(1,2,3,6),(2,3,6,11),(-1,4,3,12),(0,2,4,10),(3,-1,7,7)]
        x1,y1,x2,y2=data[v]; ans=(y2-y1)/(x2-x1)
        return "Coordinate geometry",f"Find the gradient of the line joining ({x1}, {y1}) and ({x2}, {y2}).",ans,[1/ans if ans else 1,ans+1,ans-1],f"Gradient = (y₂−y₁)/(x₂−x₁) = ({y2}−{y1})/({x2}−{x1}) = {ans:g}."
    def probability(v):
        data=[(5,4),(6,3),(7,5),(8,4),(9,6)]
        r,b=data[v]; total=r+b; ans=r/total*((r-1)/(total-1))
        return "Probability",f"A box contains {r} white and {b} black balls. Two balls are selected without replacement. Find the probability that both are white.",ans,[r/total,ans+.08,ans-.08],f"P = {r}/{total} × {r-1}/{total-1} = {ans:.4f}."
    def optimization(v):
        data=[(20,2),(30,3),(24,2),(40,4),(18,3)]
        perimeter,k=data[v]
        # rectangle with fixed perimeter and one side x; maximum area is square.
        side=perimeter/4; ans=side*side
        return "Mensuration and optimization",f"A rectangle has a fixed perimeter of {perimeter} cm. What is its maximum possible area?",ans,[perimeter**2/16+side,perimeter**2/8,ans-side],f"For a fixed perimeter, a square gives the maximum area. Side = {perimeter}/4 = {side:g} cm; area = {ans:g} cm²."
    return [integration,differentiation,logs,binomial,trig,coordinate,probability,optimization]


_build_level("JSS 1", _jss1_specs())
_build_level("JSS 2", _jss2_specs())
_build_level("JSS 3", _jss3_specs())
_build_level("SS 1", _ss1_specs())
_build_level("SS 2", _ss2_specs())
_build_level("SS 3", _ss3_specs())

assert len(QUESTION_BANK) == 240
assert all(len(q["options"]) == 4 for q in QUESTION_BANK)


# -------------------------- API request models -------------------------

class QuestionCreate(BaseModel):
    level: str = Field(..., description="JSS 1, JSS 2, JSS 3, SS 1, SS 2 or SS 3")
    subject: str = "Mathematics"
    topic: str
    question: str
    options: Dict[str, str]
    correct_answer: str
    difficulty: str = "Intermediate"
    explanation: str = ""
    marks: int = Field(default=1, ge=1)

    @field_validator("level")
    @classmethod
    def validate_level(cls, value: str) -> str:
        allowed = {"JSS 1", "JSS 2", "JSS 3", "SS 1", "SS 2", "SS 3"}
        if value not in allowed:
            raise ValueError(f"level must be one of: {', '.join(sorted(allowed))}")
        return value

    @field_validator("subject")
    @classmethod
    def mathematics_only(cls, value: str) -> str:
        if value.strip().lower() != "mathematics":
            raise ValueError("This question bank accepts Mathematics questions only.")
        return "Mathematics"

    @field_validator("options")
    @classmethod
    def validate_options(cls, value: Dict[str, str]) -> Dict[str, str]:
        if set(value.keys()) != set(LETTERS):
            raise ValueError("options must contain exactly A, B, C and D.")
        if len({str(v).strip() for v in value.values()}) != 4:
            raise ValueError("All four options must be different.")
        return value

    @field_validator("correct_answer")
    @classmethod
    def validate_correct_answer(cls, value: str) -> str:
        value = value.upper()
        if value not in LETTERS:
            raise ValueError("correct_answer must be A, B, C or D.")
        return value


# ------------------------------- API -----------------------------------

@router.get("/", summary="List Mathematics questions")
def list_questions(
    level: Optional[str] = Query(default=None, description="Filter by class, e.g. JSS 1"),
    topic: Optional[str] = Query(default=None),
    difficulty: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    results = QUESTION_BANK
    if level:
        results = [q for q in results if q["level"].lower() == level.lower()]
    if topic:
        results = [q for q in results if topic.lower() in q["topic"].lower()]
    if difficulty:
        results = [q for q in results if q["difficulty"].lower() == difficulty.lower()]
    return {
        "total": len(results),
        "limit": limit,
        "offset": offset,
        "questions": deepcopy(results[offset:offset + limit]),
    }


@router.get("/summary", summary="Get question-bank counts")
def question_summary():
    return {
        "subject": "Mathematics",
        "total_questions": len(QUESTION_BANK),
        "classes": {
            level: sum(1 for q in QUESTION_BANK if q["level"] == level)
            for level in ("JSS 1", "JSS 2", "JSS 3", "SS 1", "SS 2", "SS 3")
        },
    }


@router.get("/{question_id}", summary="Get one question")
def get_question(question_id: str):
    for question in QUESTION_BANK:
        if question["id"] == question_id:
            return deepcopy(question)
    raise HTTPException(status_code=404, detail="Question not found.")


@router.post("/", status_code=201, summary="Add a Mathematics question")
def create_question(payload: QuestionCreate):
    new_id = f"custom-math-{len(QUESTION_BANK) + 1:04d}"
    question = payload.model_dump()
    question["id"] = new_id
    QUESTION_BANK.append(question)
    return {"message": "Question added successfully.", "question": deepcopy(question)}


@router.put("/{question_id}", summary="Edit a question")
def update_question(question_id: str, payload: QuestionCreate):
    for index, existing in enumerate(QUESTION_BANK):
        if existing["id"] == question_id:
            updated = payload.model_dump()
            updated["id"] = question_id
            QUESTION_BANK[index] = updated
            return {"message": "Question updated successfully.", "question": deepcopy(updated)}
    raise HTTPException(status_code=404, detail="Question not found.")


@router.delete("/{question_id}", summary="Delete a question")
def delete_question(question_id: str):
    for index, question in enumerate(QUESTION_BANK):
        if question["id"] == question_id:
            removed = QUESTION_BANK.pop(index)
            return {"message": "Question deleted successfully.", "question_id": removed["id"]}
    raise HTTPException(status_code=404, detail="Question not found.")


@router.get("/exam/random", summary="Get a randomized CBT question set")
def random_exam(
    level: str = Query(..., description="JSS 1, JSS 2, JSS 3, SS 1, SS 2 or SS 3"),
    count: int = Query(default=40, ge=1, le=40),
):
    import random
    pool = [q for q in QUESTION_BANK if q["level"].lower() == level.lower()]
    if not pool:
        raise HTTPException(status_code=404, detail="No questions found for this class.")
    selected = random.sample(pool, min(count, len(pool)))
    # Never expose the correct answer or explanation during the live exam.
    return [
        {
            key: value for key, value in q.items()
            if key not in {"correct_answer", "explanation"}
        }
        for q in selected
    ]


def get_question_bank(level: Optional[str] = None) -> List[Dict[str, Any]]:
    """Importable helper for other services and tests."""
    if level is None:
        return deepcopy(QUESTION_BANK)
    return deepcopy([q for q in QUESTION_BANK if q["level"].lower() == level.lower()])
