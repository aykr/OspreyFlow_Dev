# Platform-b · P11 part 2: report, 11 November 2026, the Mac

1. **Built at the head named in the message**, on `lane/platform-b-p11p2` from main 1d97ea9. Not pushed. A credential step: two review rounds, listed for the owner.
2. **The gateway by default** on cloud-platform; **its own IAM identity** for Bedrock alone (a second account, its role Bedrock's two invoke actions on London's foundation models, no S3, trusted by that account alone), made only while a Bedrock engine is enabled; **no model host** allowed out until an engine is enabled.
3. **Exit:** the four strict xfails are plain tests (the stand-in's gateway holds a role only as the render gives one); the role's policy check holds no S3 action and no region but eu-west-2, red with each fault planted; cp-policy-check on the three shapes with the gateway on: in the gates (it needs Docker).
4. **Carried in from part 1, done:** the reference's per-word check; round 2's plants in `p11/plant.py` with raw output; the probe on Bedrock; the upper-case path token; the sweep's fragments; the keeps-no-key case on the rendered world.
5. **Platform's files** sent as `p11p2/cloud-platform-P11p2.diff` (harness/cloud_platform/{__init__,settings,terraform}.py, platforms/client.yaml, and P7's kind fixture). Eight cases on this branch need it, as part 1's did.
6. **Requests:** an ADR-135 amendment number for `p11p2/AS-BUILT-DRAFT.md`.
7. **Gates:** once through `stack_lease.sh offline platform-b`, the diff applied in the run's copy; results in the gate record.
