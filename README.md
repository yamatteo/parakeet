
# Context-sensitive Earley parser

### Substitution rules sensitive to their context

Context-sensitive grammars have rules like

    A B C  →  A D E C

here represented as

    &A〈 B → D E 〉&C
    
which means that *B* can be replaced by *D E* (or *D E* can match together to 
form a *B*) only if it is preceded by an *A* and followed by a *C*. This is parser,
this kind of rule is represented by having a context-free rule *〈 B → D E 〉* 
with additional expectation *&A* on the left and *&B* on the right. These 
expectations are not enforced when the rule is used but on subsequent matches:
suppose there is already a match for *&A〈 B → D E 〉&C* and there are the rules

    S  →  Z B
    R  →  A B
    
The rule for *S* cannot match because *Z* does not satisfy the expectations
of the rule used to get *B*. Instead, the rule for *R* do match, quench the 
left expectation for *A* and inherit the right expectation for *B*.

Expectations can be either positive (i.e. *&A* accept only a match with external
name *A*) or negative (i.e. *!A* accept any match but the ones with external *A*).

Substitution rules are defined as follows:


```python
from rules import SR, EX

SR(ext="B", act=("D", "E"), left=EX("&", "A"), right=EX("&", "C"))
```




    &A〈B → D E〉&C




```python
SR(ext="W", act=("Z",), right=EX("!", "C"))
```




    〈W → Z〉!C




```python
SR(ext="T", act=("A", "B", "C", "D"))
```




    〈T → A B C D〉



### Terminal rules

The second type of rules is terminal rules. They match directly to the input
(a string) using a regular expression. They do not have expectations.
They are here represented by

    〈 A → /some+ [regular] (express|on)/ 〉

Terminal rule are defined in the following way:


```python
from rules import TR

TR(ext="A", act=r"a")
```




    〈A → /a/〉




```python
TR(ext="B", act=r"[A-Z][a-z_]+")
```




    〈B → /[A-Z][a-z_]+/〉



### Matches instances

When a rule can be applied it forms a `Match` object. In the simplest case, the
rule is terminal and it match directly the string to be parsed.


```python
from rules import TR
from matches import CompleteMatch

tr = TR(ext="B", act=r"[A-Z][a-z_]+")
CompleteMatch.from_scan(rule=tr, string="Jay Earley's algorithm", start=4, name=b'\x00')
# string is always the whole string to be parsed
# start tells where the regex should begin its match
# name is a bytes name for the rule assigned by the parser
```




    ((B → /.../))1 [4:10]



The repr of the resulting object shows that is a complete match (duoble 
parenthesis) that has external name *B* which come from applying a terminal 
rule */.../* and as a depth of *1* (how many rules of type *〈 W → Z 〉* are
applied before reaching a terminal or branching with a rule such as 
*〈 Z → A B 〉*. This `CompleteMatch` does not store the text it matched to,
but remember the span of the match, shown in *[4:10]*.

Substitution rules do not create a `CompleteMatch`, they begin making a
`ForwardMatch`. For example, the rule *&A〈 B → D E 〉&C* needs many steps
to complete the match:
 - check if a match with external *A* is present to act as context on the left;
   if so, create an incomplete `ForwardMatch` _*A ( B → • D E ) &C_ where
    - _*A_ is a reference to the left-brother of the new match (i.e. a complete
      match that serves as context on the left)
    - the bullet • separate the completed matches (here none) from the
      awaited ones (here D and E)
    - _&C_ is the expectation of the match, what is needed as context on the
      right after completion
 - when a match with external _D_ is completed, check if _A_ (the
   left-brother) and _D_ can concatenate; if so, create match _*A ( B → D • E ) &C_
 - when a match _E_ is completed, check if _D_ and _E_ can concatenate; if so
   create match _*A ( B → D E • ) &C_
 - when a match _C_ is completed, check if _E_ and _C_ can concatenate; if so
   create the complete match _*A (( B → D E )) *C_; this match starts where _D_
   starts and ends where _E_ ends, but it remember that it needs _A_ on the left
   and _C_ on the right to be constructed.

All these operations are made by the parser, usually, not by the user.


```python
from rules import TR, SR, EX
from matches import CompleteMatch, ForwardMatch
from interactions import feed, settle

string = "adec"
A = CompleteMatch.from_scan(TR("A", r"a"), string, 0, b'\x00')
print(A)
```

    ((A → /.../))1 [0:1]



```python
B__ = ForwardMatch.from_rule(
    rule=SR("B", ("D", "E"), left=EX("&", "A"), right=EX("&", "C")),
    start=1,
    name=b'\x01',
    left_brother=A
)
print(B__)
```

    *A1 (B →  • D E) &C [1:1]



```python
D = CompleteMatch.from_scan(TR("D", r"d"), string, 1, b'\x02')
print(D)
```

    ((D → /.../))1 [1:2]



```python
BD_ = feed(B__, D)
print(BD_)
```

    *A1 (B → D • E) &C [1:2]



```python
E = CompleteMatch.from_scan(TR("E", r"e"), string, 2, b'\x03')
print(E)
```

    ((E → /.../))1 [2:3]



```python
BDE = feed(BD_, E)
print(BDE)
```

    *A1 (B → D E • ) &C [1:3]



```python
C = CompleteMatch.from_scan(TR("C", r"c"), string, 3, b'\x04')
print(C)
```

    ((C → /.../))1 [3:4]



```python
settle(BDE, C)
```




    *A1 ((B → D E))1 *C1 [1:3]



### Parser

Create the parser with its rules in any order, for example:


```python
from rules import TR, SR, EX
from parser import Parser

p = Parser([
        TR("a", r"a"),                              #   〈 a → /a/ 〉
        TR("b", r"b"),                              #   〈 b → /b/ 〉
        TR("c", r"c"),                              #   〈 c → /c/ 〉
        SR("C", ("c",), left=EX("&", "b")),         # &b〈 C → c 〉
        SR("C", ("c",), left=EX("&", "c")),         # &c〈 C → c 〉
        SR("B", ("b",), left=EX("&", "a")),         # &a〈 B → b 〉
        SR("B", ("b",), left=EX("&", "b")),         # &b〈 B → b 〉
        SR("W", ("B",), right=EX("&", "C")),        #   〈 W → B 〉&C
        SR("Z", ("C",), left=EX("&", "W")),         # &W〈 Z → C 〉
        SR("C", ("W",), right=EX("&", "Z")),        #   〈 C → W 〉&Z
        SR("B", ("Z",), left=EX("&", "C")),         # &C〈 B → Z 〉
        SR("S", ("a", "S", "B", "C")),              #   〈 S → a S B C 〉
        SR("S", ("a", "B", "C",)),                  #   〈 S → a B C 〉
    ])
```

and parse strings with or without the expected non-terminal


```python
p.parse("aabbcc", expect='S')
```




    [((S → a S B C))1 [0:6]]




```python
p.parse("aaaabbbbcccc")
```




    [((S → a S B C))1 [0:12]]



the output is a list of complete matches that span the whole string. If
the grammar has cycles, i.e. there are rules like _〈 A → B 〉_, _〈 B → C 〉_
and _〈 C → A 〉_, infinite renaming cycles are interrupted at the first
reappearance of the same non-terminal.

Every solution is a `CompleteMatch` that remember the rule that was applied
to make it and earlier matches it was made from.


```python
solution = p.parse("aabbcc")[0]
print(solution)
print(solution.rule)
print(solution.children)
```

    ((S → a S B C))1 [0:6]
    〈S → a S B C〉
    (((a → /.../))1 [0:1], *a1 ((S → a B C))1 *Z3 [1:4], *C4 ((B → Z))4 [4:5], *c1 ((C → c))2 [5:6])



```python
solution.children[2]
```




    *C4 ((B → Z))4 [4:5]




```python
solution.children[2].children[0]
```




    *W3 ((Z → C))3 [4:5]




```python
solution.children[2].children[0].children[0]
```




    *b1 ((C → c))2 [4:5]




```python
solution.children[2].children[0].children[0].children[0]
```




    ((c → /.../))1 [4:5]


