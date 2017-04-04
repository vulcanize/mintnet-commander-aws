# Quick script to plot blocktime vs network delay_steps
# assumes julia v0.4.5 w/ DataFrames, Plots, PyPlot, JSON
# FIXME: port to something more common, no reason for julia here really.

using DataFrames
using Plots; pyplot()
using JSON

inobj = JSON.parsefile("network_fault_output.json")

blocks = inobj["blocktimes"]
delays = inobj["delay_steps"]

df = DataFrame(t=[DateTime(block[2], "yyyy-mm-ddTHH:MM:SS.sss000+00:00") for block in blocks], 
               blocktime=[block[1] for block in blocks])
delaysdf = DataFrame(t=[DateTime(delay[2][1:23], "yyyy-mm-ddTHH:MM:SS.sss") for delay in delays], 
                     delaytime=[delay[1] for delay in delays])

tseconds = [(dt.instant.periods.value - df[:t][1].instant.periods.value) / 1000 for dt in df[:t]]
delaytseconds = [(dt.instant.periods.value - df[:t][1].instant.periods.value) / 1000 for dt in delaysdf[:t]]

timestart = min(tseconds[1], delaytseconds[1])
timeend = max(tseconds[end], delaytseconds[end])

delaytseconds = [timestart; delaytseconds]
delaysraw = [0; delaysdf[:delaytime]/1000]

plot(layout=(2,1))
plot!(tseconds, df[:blocktime], marker=:cross, label="Block time", w=3)
xlims!(timestart, timeend)
plot!(delaytseconds, delaysraw, line=:steppost, marker=:ellipse, label="Delay", subplot=2, w=3)
xlims!(timestart, timeend)
