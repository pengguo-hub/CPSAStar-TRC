"""R2-04's two soft-congestion interventions; original search code stays unchanged."""
import time

def attach_plan_observer(planner,recorder,variant):
    if variant not in ('full','control'):raise ValueError(variant)
    original=planner.segment_planner.plan_agv
    def measured(*args,**kwargs):
        aid=kwargs.get('agv_id',args[0] if args else None)
        segment=planner.segment_planner
        saved=segment.congestion_dict
        if variant=='control':segment.congestion_dict={}
        result=None
        try:
            result=original(*args,**kwargs)
            return result
        finally:
            if variant=='control':segment.congestion_dict=saved
            start=time.perf_counter()
            recorder.plan_attempts+=1
            recorder.plan_failures+=int(not(result and result[0]))
            recorder.events.append(dict(event='plan',time=planner.current_time,agent=aid,
                request=recorder.active.get(aid),success=bool(result and result[0]),
                wait_field_enabled=variant=='full'))
            recorder.overhead_seconds+=time.perf_counter()-start
    planner.segment_planner.plan_agv=measured

def before_batch(planner,variant):
    # Native loop sets USE_CON=True after advancing. Disable only the control
    # arm's congestion priority read at the next batch; base/age terms remain.
    if variant=='control':planner.USE_CON=False
