---
title: CShape::RemoveShape
position: 2.1
type: fn
description: Remove a shape
right_code: |
  ~~~ cpp
    void RemoveShape(int index)
  ~~~
  {: title="Signatures" }
---
`int` index
: The index of the shape to remove. The base shape has index `0`.

Removing a shape that doesn't exist might cause an engine crash.  
Removing the base shape [might cause an engine crash](https://forum.thd.vg/threads/obscure-cshape-removeshape-method.26842/#post-398399).  
`CShape::AddShape` doesn't seem to behave instantly, so you might need to wait at least next tick before removing a shape that was just added. [Link](https://forum.thd.vg/threads/obscure-cshape-removeshape-method.26842/#post-398411)  
Furthermore, removing a shape might have side-effects later, such as the deleted shape reappearing. [Link](https://forum.thd.vg/threads/obscure-cshape-removeshape-method.26842/#post-398681)  
For those reasons, this function *should not* be used.
{: .error }
