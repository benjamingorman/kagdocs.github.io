---
title: CBlob::setAngleDegrees
position: 1.1
type: fn
description: Set the blob angle in degrees
right_code: |
  ~~~ cpp
    void setAngleDegrees(float angle)
  ~~~
  {: title="Signatures" }
---
`float` angle
: The angle in degrees to apply to the blob.

The angle can still be set though the `CShape` rotations are disabled (through `CShape::SetRotationsAllowed`).  
{: .info }

This function has to be called client-side as well when handling player blobs, otherwise only other players will see the sprite rotated.
{: .info }

A positive angle value will rotate the blob clockwise.
