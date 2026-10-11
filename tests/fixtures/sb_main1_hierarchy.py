# main.py is run by parallel.py

from pathlib import Path
import glob
import copy
import csv
import numpy as np
import pandas as pd
import blast
import os

conf = blast.settings



# ----- default worker_name and map function -----
    
def get_worker_name():
    from datetime import datetime
    date = datetime.now().strftime("%Y%b%d")
    return 'serial_%s'%date
parallel_map = map
blast.runtime['get_worker_name'] = get_worker_name
model_dict = blast.json.read(conf["model"])
blast.runtime["FF"] = blast.model.load_from_dict(model_dict)

#----- create ram based tmp -----
if not 'ramtmp' in blast.runtime:
    import tempfile, os, shutil
    from pathlib import Path
    tmp_dir = blast.conf.get('lmp',{}).get('tmp_dir','tmp')
    p_tmp = Path(tmp_dir)
    if p_tmp.is_symlink():
        blast.runtime['ramtmp'] = str(p_tmp.resolve())
    else:
        if p_tmp.exists():
            shutil.rmtree(p_tmp) if p_tmp.is_dir() else p_tmp.unlink()
        tmp = tempfile.mkdtemp(prefix="blastff_",dir='/dev/shm')
        if not Path(tmp).exists():
            blast.mpy.ERROR(f"cannot create tmp directory,\n{tmp}")
        else:
            blast.logger.info(f"ram based tmp directory at {tmp}")
        try:
            blast.cmd.ln(tmp, tmp_dir)
        except Exception:
            blast.mpy.ERROR(f"cannot symlink {tmp} to '{tmp_dir}'")
        blast.runtime['ramtmp'] = tmp
    
    
# ----- define objective -----
def objective(params):
    
    runtime = blast.runtime
    wkr = runtime['get_worker_name']
    worker = runtime['worker'][wkr()]

    # force field
    FF = runtime['FF']
    
    # initialize report
    if not 'HO' in worker:
        HO = worker['HO'] = blast.data.load('ho').setup()
        report_dir = conf.get('data',{}).get('report_dir', 'reports')
        HO.reportfile = f"{report_dir}/ho.report"
        HO.write(str(FF),prefix='# ')
    else:
        HO = worker['HO']

    # initialize training data
    if not 'GEO' in worker:
        GEO = worker['GEO'] = blast.data.load('structure').catalog()
        GEO.path = blast.conf['data']['path']
    else:
        GEO = worker['GEO']

    # clear working directory
    tmp_dir = blast.conf.get('lmp',{}).get('tmp_dir','tmp')
    wd = worker['wd'] = blast.cwd/f"{tmp_dir}/{wkr()}"
    blast.cmd.mkdir(wd,reset=True)

    # reset
    HO.reset()
    GEO.reset()


#    while FF.get() is None: True
    if FF.get(params) is None: return HO.finalobj()
    FF.write(wd/'trial.ff',verbose=False)
    param_str = ' '.join([str(s) for s in params]) + ' DUMP'
    
    
    workflow = blast.conf.get('data',{}).get('workflow',[])
    earlyexit = bool(blast.conf.get('data',{}).get('earlyexit',True))
    if not earlyexit:
        scores, failed = [], []


    # ----------------------- workflow --------------------
    polymorphs_energy_order = sorted([
        Path(fname).name for fname in
        glob.glob(GEO.path+'/*.data')
    ], key=lambda s:int(s.split('/')[-1].split('.')[0]))
    

    polymorphs_energy_order=list(polymorphs_energy_order[i] for i in [0])
    
    print(polymorphs_energy_order)
    
    

    #PROPERTY CALCULATION: Lattice Parameters

    prop = 'lattice'
    
    w_stage = np.ones(len(polymorphs_energy_order))

    kwargs = {
        "in|onoff_log": '#',
        "in|replicate": '6 6 1',
        "in|reset": True,
        "in|onoff_boxrelax": '',
        "in|P_couple": 'none',
    }

    for structure in polymorphs_energy_order:

        geo = GEO[structure]
        c=structure[0]

        # target
        _t = geo.compute(prop, suffix='_t', verbose=False)
        if _t is SystemExit:
            return HO.finalobj('runtime error')

       

        # predicted
        _p = geo.compute(prop, suffix='_p', **kwargs, verbose=False)
        if _p is SystemExit:
            return HO.finalobj('runtime error')



        # scoring
        _s = geo.score(prop,tally=True,w_stage=w_stage)
        if _s is SystemExit:
            return HO.finalobj('runtime error')
            


        # checkpoint
        _failed = geo.checkpoint(prop,**{"conditions": [
            "values.maxAE% <= 3",
        ]})
        

        if earlyexit and _failed:
            return HO.finalobj(f"{param_str} {structure.split('.')[0]}/{polymorphs_energy_order[-1].split('.')[0]} {prop} maxAE > 3%")
        elif not earlyexit:
            failed.append(_failed)
            
        

    # PROPERTY CALCULATION: Cohesive Energy and Ordering

    prop = 'ce'
    

    kwargs = {
        "in|onoff_log": '#',
        "in|reset": True,
        "in|replicate": '6 6 1',
        "in|onoff_boxrelax": '',
        "in|P_couple": 'none',
        "in|onoff_min": '',
    }

    w_stage = np.ones(len(polymorphs_energy_order)) # +1 for ordering
    group = blast.data.load('geo').group()
    for structure in polymorphs_energy_order:
       

        geo = GEO[structure]
        struct_label = geo.meta["label"]
        c=structure[0]
        
        # target
        _t = geo.compute(prop, suffix='_t', verbose=False)
        if _t is SystemExit:
            return HO.finalobj('runtime error')
        

        for s in _t:
            group._t[s].append(_t[s])

        

        # predicted
        _p = geo.compute(prop, suffix='_p', **kwargs, verbose=False)
        if _p is SystemExit:
            return HO.finalobj('runtime error')

        
        for s in _p:
            group._p[s].append(_p[s])
    # scoring
 
    # checkpoint
        

    _s = group.score(prop,tally=True,  w_stage=w_stage, w_typ={'ordering': 0.5, 'values': 1}, typ=['ordering', 'values'])
    _failed = group.checkpoint(prop,**{"conditions": ["ordering.Norderoff==0", "values.maxAE%<=3"]})

    if _s is SystemExit:
        return HO.finalobj('runtime error')


    if earlyexit and _failed:
        return HO.finalobj(f"{param_str} {structure.split('.')[0]}/{polymorphs_energy_order[-1].split('.')[0]} {prop} maxAE% > 3%")
    elif not earlyexit:
        failed.append(_failed)
    


    # PROPERTY CALCULATION: Equation of State
    prop = 'eos'
    
    for structure in polymorphs_energy_order[:1]:
        

        geo = GEO[structure]

        # target
        _t = geo.compute(prop, suffix='_t', verbose=False)
        if _t is SystemExit:
            return HO.finalobj('runtime error')

          
        # predicted
        _p = geo.compute(prop, suffix='_p', strain_basis="a b", verbose=False)
        # print(_p)
        if _p is SystemExit:
            return HO.finalobj('runtime error')

        
        # scoring
        _s = geo.score(prop,tally=True)
        if _s is SystemExit:
            return HO.finalobj('runtime error')
        
        
        
        # checkpoint
        _failed = geo.checkpoint(prop,**{"conditions": [
            "shape.obj <= 166", "shift.obj <= 28"
        ]})

        if earlyexit and _failed:

            return HO.finalobj(f"{param_str} {structure.split('.')[0]}/{polymorphs_energy_order[-1].split('.')[0]} {prop} failed")
        elif not earlyexit:
            failed.append(_failed)
        
# PROPERTY CALCULATION: msd

    # prop = 'msd'
    

    # in_par = {
    #     "onoff_log": '',
    #     'onoff_msd': '',
    #     "reset": True,
    #     "replicate": '6 6 1',
    #     "onoff_boxrelax": '',
    #     "P_couple": 'none',
    #     "onoff_min": '',
    #     "onoff_eq":'',
    #     'eq_ensemble': 'npt',
    #     'P': 0,
    #     'T': 300,
    #     'timestep': {'metal': 0.0005},
    #     'run': 4e3,
    #     "P_couple": 'xy',
    # }

    # w_stage = np.ones(len(polymorphs_energy_order)) # +1 for ordering
    # group = blast.data.load('geo').group()
    # for structure in polymorphs_energy_order[:1]:
       

    #     geo = GEO[structure]
    #     struct_label = geo.meta["label"]
    #     c=structure[0]
        
    #     # target
        
    #     geo1=geo.min_eq(in_par)
        

    #     # print(f"Data written to {output_file_path}")

        
    #     print(geo1.data['c_msd[4]'][-1])
    #     # quit()
        

    #     var=HO.score({"t":0.1,"p":geo1.data['c_msd[4]'][-1]}, typ="values")
    #     # HO.stageobj(var['values.obj'], "msd")
    #     msd_failed=var["values.maxAE%"]>=700
        
    #     if earlyexit and msd_failed:
    #         return HO.finalobj(f"{param_str} {structure.split('.')[0]}/{polymorphs_energy_order[-1].split('.')[0]} {prop} maxAE > 700%")
    #     elif not earlyexit:
    #         failed.append(_failed)


    # PROPERTY CALCULATION: Elastic Constants
    # prop = 'elastic'
    
    # for structure in polymorphs_energy_order[:1]:
        
    #     geo = GEO[structure]
    #     geo_prop = geo.meta['prop']
    #     c=structure[0]
    #     if not 'elastic' in geo_prop: continue
            
    #     # target
    #     _t = geo.compute(prop, suffix='_t', verbose=False)
        

    #     if _t is SystemExit:
    #         return HO.finalobj('runtime error')
    #     w_elastic=np.abs(_t['elastic_t'])+1

        

    #     # predicted
    #     _p = geo.compute(prop, suffix='_p', up=1e-6, verbose=False)

        
    #     if _p is SystemExit:
    #         return HO.finalobj('runtime error')


    #     # scoring
    #     _s = geo.score(prop,tally=True,  w=np.array([1,1,0,1,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0]))
    #     if _s is SystemExit:
    #         return HO.finalobj('runtime error')
        
            
    #     # checkpoint
    #     _failed = geo.checkpoint(prop,**{"conditions": [
    #         "values.MAE% <= 30"
    #     ]})

    #     # #checkpoint
    #     # _failed = geo.checkpoint(prop,**{"conditions": [
    #     #         "values.MAE% <= 100",
    #     # ]})
        

    #     if earlyexit and _failed:
    #         return HO.finalobj(f"{param_str} {structure.split('.')[0]}/{polymorphs_energy_order[-1].split('.')[0]} {prop} MAE% > 25")
    #     elif not earlyexit:
    #         failed.append(_failed)
    
     
                        
    # PROPERTY CALCULATION: Phonon Dispersion
    prop = 'phonon'
    
    # each structure is a substage, weighted by w

    structures_with_phonon = [
        s for s in polymorphs_energy_order 
        if 'phonon' in GEO[s].meta['prop']
    ]

    w_stage = np.ones(len(structures_with_phonon))
    for structure in structures_with_phonon[:1]:
      
        geo = GEO[structure]
            
        _t = geo.compute(
            'phonon', suffix='_t',
            png = 'phonon_t.png',
            txt = 'phonon_t.txt',
        )
        #print(_t)
        # print(type(_t))
        
        
        
        if _t is SystemExit:
            return HO.finalobj('runtime error')

        _p = geo.compute(
            'phonon', suffix='_p',
            verbose = False,
            png = 'phonon_p.png',
            txt = 'phonon_p.txt',
            savedat = 'phonon_p',
            savedos = True,
            saveCv = 'Cv_p.txt',
        )
        
        if _p is SystemExit:
            return HO.finalobj('runtime error')
        #print(_p)
        # print(type(_p))

        _s = geo.score(prop,{**geo._t, **geo._p}, w_stage=w_stage, w_aco=0.8, w_opt=0.2)
        
        if _s is SystemExit:
            return HO.finalobj('runtime error')

        phonon = blast.data.load('phonon')
        phonon.plot({**_t,**_p},f'plot_{structure}.png')
    
        _failed =  geo.checkpoint('phonon',conditions = [
            #"phonon_Nneg_p == 0",
            # "shape.obj <= 20.0820",
            # "phonon_Nneg_p <= 1.1*phonon_Nneg_t",
            # "gamma.Nwayoff == 0",
            # "gap.maxAE%' <= 60",
            # "gap_lo.maxAE% <= 60",
            # "gamma.maxAE% <= 200",
            "ceil.maxAE% <= 30.20",
        ])
        _failed1 = _s["obj"]>=128
        # a = (HO.lastfinalobj(f"{param_str} completed all stages"))
        
            
        if earlyexit and (_failed or _failed1):
            return HO.finalobj(f"{param_str} {structure.split('.')[0]}/{polymorphs_energy_order[-1].split('.')[0]} phonon failed")
        elif not earlyexit:
            failed.append(_failed)
            
            
        # PROPERTY CALCULATION: Elastic Constants
    prop = 'elastic'
    
    for structure in polymorphs_energy_order[:1]:
        
        geo = GEO[structure]
        geo_prop = geo.meta['prop']
        c=structure[0]
        if not 'elastic' in geo_prop: continue
            
        # target
        _t = geo.compute(prop, suffix='_t', verbose=False)
        

        if _t is SystemExit:
            return HO.finalobj('runtime error')
        w_elastic=np.abs(_t['elastic_t'])+1

        

        # predicted
        _p = geo.compute(prop, suffix='_p', up=1e-6, verbose=False)

        
        if _p is SystemExit:
            return HO.finalobj('runtime error')


        # scoring
        _s = geo.score(prop,tally=True,  w=np.array([1,1,0,1,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0]))
        if _s is SystemExit:
            return HO.finalobj('runtime error')
        
            
        # checkpoint
        _failed = geo.checkpoint(prop,**{"conditions": [
            "values.MAE% <= 30"
        ]})

        # #checkpoint
        # _failed = geo.checkpoint(prop,**{"conditions": [
        #         "values.MAE% <= 100",
        # ]})
        

        if earlyexit and _failed:
            return HO.finalobj(f"{param_str} {structure.split('.')[0]}/{polymorphs_energy_order[-1].split('.')[0]} {prop} MAE% > 25")
        elif not earlyexit:
            failed.append(_failed)

    
   
    
    return HO.lastfinalobj(f"{param_str} completed all stages")

blast.runtime['objective'] = objective

if __name__ == '__main__':
    import sys
    print(sys.argv[1:])
    objective(sys.argv[1:])
