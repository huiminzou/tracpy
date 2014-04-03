import numpy as np
import op
import netCDF4 as netCDF
import pdb
from tracpy.time_class import Time

def run(tp, date, lon0, lat0):
    '''
    FIX THIS FOR USING TRACPY CLASS
    To re-compile tracmass fortran code, type "make clean" and "make f2py", which will give 
    a file tracmass.so, which is the module we import above. Then in ipython, "run run.py"
    xend,yend,zend are particle locations at next step
    some variables are not specifically because f2py is hiding them from me:
     imt, jmt, km, ntractot
    Look at tracmass.step to see what it is doing and making optional at the end.
    Do this by importing tracmass and then tracmass.step?

    I am assuming here that the velocity field at two times are being input into tracmass
    such that the output is the position for the drifters at the time corresponding to the
    second velocity time. Each drifter may take some number of steps in between, but those
    are not saved.

    tp          TracPy object, from the Tracpy class.

    loc         Path to directory of grid and output files
    nsteps      Number of steps to do between model outputs (iter in tracmass) - sets the max 
                time step between drifter steps. Does not control the output sampling anymore.
    ndays       number of days to track the particles from start date
    ff          ff=1 to go forward in time and ff=-1 for backward in time
    date        Start date in datetime object
    tseas       Time between outputs in seconds
    ah          Horizontal diffusion in m^2/s. 
                See project values of 350, 100, 0, 2000. For -turb,-diffusion
    av          Vertical diffusion in m^2/s.
    do3d        for 3d flag, do3d=0 makes the run 2d and do3d=1 makes the run 3d
    doturb      turbulence/diffusion flag. 
                doturb=0 means no turb/diffusion,
                doturb=1 means adding parameterized turbulence
                doturb=2 means adding diffusion on a circle
                doturb=3 means adding diffusion on an ellipse (anisodiffusion)
    lon0        Drifter starting locations in x/zonal direction.
    lat0        Drifter starting locations in y/meridional direction.
    z0/zpar     For 3D drifter movement, turn off twodim flag in makefile.
                Then z0 should be an array of initial drifter depths. 
                The array should be the same size as lon0 and be negative
                for under water. Currently drifter depths need to be above 
                the seabed for every x,y particle location for the script to run.
                To do 3D but start at surface, use z0=zeros(ia.shape) and have
                 either zpar='fromMSL'
                choose fromMSL to have z0 starting depths be for that depth below the base 
                time-independent sea level (or mean sea level).
                choose 'fromZeta' to have z0 starting depths be for that depth below the
                time-dependent sea surface. Haven't quite finished the 'fromZeta' case.
                For 2D drifter movement, turn on twodim flag in makefile.
                Then: 
                set z0 to 's' for 2D along a terrain-following slice
                 and zpar to be the index of s level you want to use (0 to km-1)
                set z0 to 'rho' for 2D along a density surface
                 and zpar to be the density value you want to use
                 Can do the same thing with salinity ('salt') or temperature ('temp')
                 The model output doesn't currently have density though.
                set z0 to 'z' for 2D along a depth slice
                 and zpar to be the constant (negative) depth value you want to use
                To simulate drifters at the surface, set z0 to 's' 
                 and zpar = grid['km']-1 to put them in the upper s level
                 z0='s' is currently not working correctly!!!
                 In the meantime, do surface using the 3d set up option but with 2d flag set
    zparuv      (optional) Use this if the k index for the model output fields (e.g, u, v) is different
                 from the k index in the grid. This might happen if, for example, only the surface current
                 were saved, but the model run originally did have many layers. This parameter
                 represents the k index for the u and v output, not for the grid.
    tseas_use   (optional) Desired time between outputs in seconds, as opposed to the actual time between outputs
                 (tseas). Should be >= tseas since this is just an ability to use model output at less 
                 frequency than is available, probably just for testing purposes or matching other models.
                 Should to be a multiple of tseas (or will be rounded later).
    savell      (True) True to save drifter tracks in lon/lat and False to save them in grid coords
    doperiodic  (0) Whether to use periodic boundary conditions for drifters and, if so, on which walls.
                0: do not use periodic boundary conditions
                1: use a periodic boundary condition in the east-west/x/i direction
                2: use a periodic boundary condition in the north-south/y/j direction
    units       ('seconds since 1970-01-01') Units for time conversion with netCDF.num2date and .date2num

    xp          x-locations in x,y coordinates for drifters
    yp          y-locations in x,y coordinates for drifters
    zp          z-locations (depths from mean sea level) for drifters
    t           time for drifter tracks
    name        Name of simulation to be used for netcdf file containing final tracks
    grid        (optional) Grid information, as read in by tracpy.inout.readgrid().
    N           Controls the output sampling. The length of time between model outputs is divided by N.
                Default is 1.

    The following inputs are for calculating Lagrangian stream functions
    dostream    Calculate streamfunctions (1) or not (0). Default is 0.
    U0, V0      (optional) Initial volume transports of drifters (m^3/s)
    U, V  (optional) Array aggregating volume transports as drifters move [imt-1,jmt], [imt,jmt-1]
    '''

    timer = Time() # start timer for simulation

    # Initialize everything for a simulation
    tinds, nc, t0save, xend, yend, zend, zp, ttend, flag = tp.prepare_for_model_run(date, lon0, lat0)

    timer.addtime('1: Preparing for simulation   ')

    # Loop through model outputs. tinds is in proper order for moving forward
    # or backward in time, I think.
    for j,tind in enumerate(tinds[:-1]):

        print j

        # Loop through substeps in call to TRACMASS in case we want to add on windage, etc, for each step
        for nsubstep in xrange(tp.nsubsteps):

            xstart, ystart, zstart, ufsub, vfsub = tp.prepare_for_model_step(tinds[j+1], nc, flag, xend, yend, zend, j, nsubstep)
            ind = (flag[:] == 0) # indices where the drifters are still inside the domain

            timer.addtime('2: Preparing for model step   ')

            if not np.ma.compressed(xstart).any(): # exit if all of the drifters have exited the domain
                break

            # Do stepping in Tracpy class
            xend_temp,\
                yend_temp,\
                zend_temp,\
                flag[ind],\
                ttend_temp, U, V = tp.step(xstart, ystart, zstart, ufsub, vfsub)

            timer.addtime('3: Stepping, using TRACMASS   ')

            xend[ind,j*tp.N+1:j*tp.N+tp.N+1], \
                yend[ind,j*tp.N+1:j*tp.N+tp.N+1], \
                zend[ind,j*tp.N+1:j*tp.N+tp.N+1], \
                zp[ind,j*tp.N+1:j*tp.N+tp.N+1], \
                ttend[ind,j*tp.N+1:j*tp.N+tp.N+1] = tp.model_step_is_done(xend_temp, yend_temp, zend_temp, ttend_temp, ttend[ind,j*tp.N])

            timer.addtime('4: Processing after model step')

    nc.close()

    lonp, latp, zp, ttend, grid, T0, U, V = tp.finishSimulation(ttend, t0save, xend, yend, zp)

    timer.addtime('5: Processing after simulation')

    print "============================================="
    print ""
    print "Simulation name: ", tp.name
    print ""
    print "============================================="

    timer.write()

    return lonp, latp, zp, ttend, grid, T0, U, V
