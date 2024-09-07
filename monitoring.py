import sys
import ROOT
ROOT.gROOT.SetBatch(True)
import time
import signal
import os
import random

running = True

# Define a signal handler function
def handle_stop_signal(signal, frame):
    global running
    running = False
    print("Stop signal received. Exiting...")

class hit:
    def __init__(self, board, channel, low_gain, high_gain, timestamp, trigger_id):
        self.board = int(board)
        self.channel = int(channel)
        
        self.gain_ratio = 9.5
        self.low_gain = int(low_gain)
        self.high_gain = int(high_gain)
        self.comb_gain = int(high_gain)
        if self.comb_gain >= 3800:
            self.comb_gain = (self.low_gain + int(random.random()))* self.gain_ratio
        
        self.timestamp = float(timestamp)
        self.trigger_id = int(trigger_id)

        self.x = (self.channel % 8)
        if self.x > 3:
            self.x = 7 - self.x

        self.y = (self.channel % 8)
        if self.y > 3:
            self.y = 0
        else:
            self.y = 1

        self.z = self.board * 8 + (7 - int(self.channel / 8))

class event:
    def __init__(self, event_number):
        self.event_number = event_number
        self.hits = [None] * 512
        self.hits_found = 0
        self.max_adc = 0

    def add_hit(self, hit):
        self.hits[hit.channel + 64 * hit.board] = hit
        self.hits_found += 1
        if hit.high_gain > self.max_adc:
            self.max_adc = hit.high_gain

    def is_complete_event(self):
        return self.hits_found == 512

    

class file_parser:
    def __init__(self, file_path):
        self.file_path = file_path
        self.line_number = 0

    # Define context manager methods
    def __enter__(self):
        self.file = open(self.file_path, 'r')
        # Skip first 9 lines
        for _ in range(9):
            self.file.readline()
            self.line_number += 1
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        self.file.close()

    # Define iterator methods
    def __iter__(self):
        return self
    
    def __next__(self):
        # First, get the summary line
        try:
            line = self.file.readline().strip()
            self.line_number += 1
            if not line:
                return None
                # raise StopIteration
            board, channel, low_gain, high_gain, timestamp, trigger_id, nhits = line.split()
            hits = [None] * int(nhits)
            hits[int(channel)] = hit(board, channel, low_gain, high_gain, timestamp, trigger_id)
            
            # Then, get the rest of the hits
            for i in range(1, int(nhits)):
                line = self.file.readline().strip()
                self.line_number += 1
                if not line:
                    return None
                board, channel, low_gain, high_gain = line.split()
                hits[int(channel)] = hit(board, channel, low_gain, high_gain, timestamp, trigger_id)
            return hits
        except ValueError:
            print(f"Error parsing line {self.line_number}: {line}")
            return None
    


class online_monitor:
    def __init__(self, file_path, run_number, caen_units=8, channels=64):
        self.run_number = run_number
        # Set up the output file
        output_path = f"output/run{run_number}"
        if not os.path.exists(output_path):
            os.makedirs(output_path)
        
        self.output_file = ROOT.TFile(f"{output_path}/run{run_number}.root", "RECREATE")

        self.events = {}

        self.file_path = file_path
        self.caen_units = caen_units
        self.channels = channels

        monitoring_port = int(os.environ.get('MONITORING_PORT', 54321))
        self.server = ROOT.THttpServer(f'http:{monitoring_port}')
        
        self.low_gain_histograms = []
        self.high_gain_histograms = []
        self.combined_gain_histograms = []
        self.gain_correlations = []

        self.num_events = []
        self.missed_events = []
        self.num_hits = [0] * caen_units
        self.last_hits = []
        for i in range(caen_units):
            self.last_hits.append([hit(i, 0, 0, 0, 0, 0)] * channels)

        self.overview_high_gain = None
        self.overview_low_gain = None
        self.overview_combined_gain = None

        self.event_display = None
        self.event_display_combined_gain = None

        self.canvases = []

        self.text = ROOT.TLatex()
        self.text.SetTextSize(0.1)
        # self.SetFont(42)
        self.text.SetTextAlign(33)

        # Create histograms
        for i in range(caen_units):
            caen_lg_histograms = []
            caen_hg_histograms = []
            caen_cg_histograms = []
            caen_correlation_histograms = []


            for j in range(channels):
                lg_histogram = ROOT.TH1F(f'caen_{i}_ch_{j}_lg', f'CAEN {i} Channel {j} Low Gain', 4096//4, 0, 4096)
                hg_histogram = ROOT.TH1F(f'caen_{i}_ch_{j}_hg', f'CAEN {i} Channel {j} High Gain', 4096//4, 0, 4096)
                cb_histogram = ROOT.TH1F(f'caen_{i}_ch_{j}_cb', f'CAEN {i} Channel {j} Combined Gain', 40001, 0, 40001)
                correlation_hist = ROOT.TH2F(f'caen_{i}_ch_{j}_correlation', f'CAEN {i} Channel {j} Correlation;High Gain;Low Gain', 512, 0, 4096, 256, 0, 512)
                self.server.Register(f'/individual/low_gain/caen_{i}', lg_histogram)
                self.server.Register(f'/individual/high_gain/caen_{i}', hg_histogram)
                self.server.Register(f'/individual/combined_gain/caen_{i}', cb_histogram)
                self.server.Register(f'/individual/correlation/caen_{i}', correlation_hist)
                caen_lg_histograms.append(lg_histogram)
                caen_hg_histograms.append(hg_histogram)
                caen_cg_histograms.append(cb_histogram)
                caen_correlation_histograms.append(correlation_hist)
                

            self.low_gain_histograms.append(caen_lg_histograms)
            self.high_gain_histograms.append(caen_hg_histograms)
            self.combined_gain_histograms.append(caen_cg_histograms)
            self.gain_correlations.append(caen_correlation_histograms)

        for i in range(caen_units):
            lg_canvas = ROOT.TCanvas(f'caen_{i}_lg', f'CAEN {i} Low Gain', 1200, 800)
            hg_canvas = ROOT.TCanvas(f'caen_{i}_hg', f'CAEN {i} High Gain', 1200, 800)
            cb_canvas = ROOT.TCanvas(f'caen_{i}_cb', f'CAEN {i} Combined Gain', 1200, 800)
            corr_canvas = ROOT.TCanvas(f'caen_{i}_corr', f'CAEN {i} Correlation', 1200, 800)
            lg_canvas.Divide(8, 8, 0, 0)
            hg_canvas.Divide(8, 8, 0, 0)
            cb_canvas.Divide(8, 8, 0, 0)
            corr_canvas.Divide(8, 8, 0, 0)
            for j in range(channels):
                # Draw low gain
                lg_canvas.cd(j+1)
                self.low_gain_histograms[i][j].Draw()
                self.label_channel(i, j)
                ROOT.gPad.SetLogy()
                # Draw high gain
                hg_canvas.cd(j+1)
                ROOT.gPad.SetLogy()
                self.high_gain_histograms[i][j].Draw()
                self.label_channel(i, j)
                # Draw combined gain
                cb_canvas.cd(j+1)
                ROOT.gPad.SetLogy()
                self.combined_gain_histograms[i][j].Draw()
                self.label_channel(i, j)
                # Draw correlation
                corr_canvas.cd(j+1)
                self.gain_correlations[i][j].Draw('col')
                self.label_channel(i, j)

            self.server.Register(f'/overview/low_gain', lg_canvas)
            self.server.Register(f'/overview/high_gain', hg_canvas)
            self.server.Register(f'/overview/combined_gain', cb_canvas)
            self.server.Register(f'/overview/correlation', corr_canvas)
            self.canvases.append(lg_canvas)
            self.canvases.append(hg_canvas)
            self.canvases.append(cb_canvas)
            self.canvases.append(corr_canvas)

        multi_graph = ROOT.TMultiGraph()
        # i = 0
        canvas = ROOT.TCanvas(f'num_events_caen', f'Number of Events', 1200, 800)
        canvas_2 = ROOT.TCanvas(f'missed_events_caen', f'Missed Events', 1200, 800)
        line_colors = [ROOT.kRed, ROOT.kBlue, ROOT.kGreen + 2, ROOT.kMagenta]
        line_styles = [ROOT.kSolid, ROOT.kDashed]
        line_styles_2 = [ROOT.kDotted, ROOT.kDashDotted]
        legend = ROOT.TLegend(0.1, 0.7, 0.48, 0.9)
        legend.SetLineWidth(0)
        self.canvases.append(legend)
        self.canvases.append(canvas)
        self.canvases.append(canvas_2)
        for i in range(caen_units):
            canvas.cd()
            number_events = ROOT.TGraph()
            number_events.SetTitle(f'Number of Events Run {run_number}')
            number_events.SetName(f'caen_{i}_num_events')
            number_events.GetXaxis().SetTimeDisplay(1)
            number_events.GetXaxis().SetTimeFormat('%H:%M:%S')
            number_events.SetLineColor(line_colors[i % 4])
            number_events.SetLineStyle(line_styles[int(i / 4)])
            number_events.SetLineWidth(2)
            number_events.GetYaxis().SetRangeUser(0, 100000)
            legend.AddEntry(number_events, f'CAEN {i}', 'l')
            if i == 0:
                number_events.Draw("AL")
            else:
                number_events.Draw("L")


            canvas_2.cd()
            ROOT.gROOT.Add(number_events)
            self.num_events.append(number_events)
            missed_events = ROOT.TGraph()
            missed_events.SetTitle(f'Fraction of Events Run {run_number}')
            missed_events.SetName(f'caen_{i}_num_events')
            missed_events.GetXaxis().SetTimeDisplay(1)
            missed_events.GetXaxis().SetTimeFormat('%H:%M:%S')
            missed_events.SetLineColor(line_colors[i % 4])
            missed_events.SetLineStyle(line_styles_2[int(i / 4)])
            missed_events.SetLineWidth(2)
            if i == 0:
                missed_events.Draw("AL")
            else:
                missed_events.Draw("L")
            missed_events.GetYaxis().SetRangeUser(0, 1)
            ROOT.gROOT.Add(missed_events)
            self.missed_events.append(missed_events)
        canvas.cd()
        legend.Draw()
        canvas_2.cd()
        legend.Draw()
        self.server.Register('/overview/num_events', canvas)
        self.server.Register('/overview/num_events', canvas_2)
        # multi_graph.Add(number_events)

        canvas = ROOT.TCanvas(f'Overview HG', f'Overview HG', 1200, 800)
        canvas.SetLogz()
        self.overview_high_gain = ROOT.TH2F('overview_high_gain', 'Overview HG', caen_units*100, 0, caen_units*100, 4096, 0, 4096)
        self.overview_high_gain.Draw("COLZ")
        self.server.Register('/overview/AllAtOnce', canvas)
        self.canvases.append(canvas)

        canvas2 = ROOT.TCanvas(f'Overview LG', f'Overview LG', 1200, 800)
        canvas2.SetLogz()
        self.overview_low_gain = ROOT.TH2F('overview_low_gain', 'Overview LG', caen_units*100, 0, caen_units*100, 4096, 0, 4096)
        self.overview_low_gain.Draw("COLZ")
        self.server.Register('/overview/AllAtOnce', canvas2)
        self.canvases.append(canvas2)

        canvas3 = ROOT.TCanvas(f'Overview CombG', f'Overview CombG', 1200, 800)
        canvas3.SetLogz()
        self.overview_combined_gain = ROOT.TH2F('overview_comb_gain', 'Overview CombG', caen_units*100, 0, caen_units*100, 40000, 0, 40000)
        self.overview_combined_gain.Draw("COLZ")
        self.server.Register('/overview/AllAtOnce', canvas3)
        self.canvases.append(canvas3)
        
        # canvas = ROOT.TCanvas('num_events', 'Number of Events', 1200, 800)
        # canvas.cd()
        # multi_graph.GetXaxis().SetTimeDisplay(1)
        # multi_graph.GetXaxis().SetTimeFormat('%H:%M:%S')
        # multi_graph.Draw('AL PLC')
        # self.server.Register('/overview/num_events', canvas)
        # self.num_events.append(multi_graph)

        canvas = ROOT.TCanvas('event_display', 'Event Display', 1200, 800)
        self.event_display = ROOT.TH3F('event_display', 'Event Display', 66, 0, 66, 4, 0, 4, 2, 0, 2)
        self.event_display.SetBinContent(1, 1, 1, 1)
        self.event_display.SetBinContent(5, 1, 1, 40000)
        self.event_display.SetMinimum(0)
        self.event_display.SetMaximum(40000)
        self.event_display.SetContour(99)
        self.event_display.Draw("BOX2Z")
        self.event_display.SetContour(99)
        self.event_display.SetStats(0)
        self.server.Register('/overview/event_display', canvas)
        self.canvases.append(canvas)

        canvas2 = ROOT.TCanvas('event_display_comb', 'Event Display Comb', 1200, 800)
        self.event_display_comb = ROOT.TH3F('event_display_comb', 'Event Display Comb gain', 66, 0, 66, 4, 0, 4, 2, 0, 2)
        # self.event_display_comb.SetMinimum(0)
        # self.event_display_comb.SetMaximum(40000)
        self.event_display_comb.SetStats(0)
        self.event_display_comb.Draw("BOX2Z")
        self.server.Register('/overview/event_display', canvas2)
        self.canvases.append(canvas2)

    def label_channel(self, caen, channel):
        self.text.DrawLatexNDC(0.95, 0.85, f'Run {self.run_number}')
        self.text.DrawLatexNDC(0.95, 0.75, f'CAEN {caen}')
        self.text.DrawLatexNDC(0.95, 0.65, f'Channel {channel}')

    def close(self):
        self.output_file.Write()
        self.output_file.Close()

    def update(self):
        max = 0
        for i in range(self.caen_units):
            self.num_events[i].SetPoint(self.num_events[i].GetN(), ROOT.TDatime().Convert(), self.last_hits[i][0].trigger_id)
            if self.last_hits[i][0].trigger_id > max:
                max = self.last_hits[i][0].trigger_id
        for i in range(self.caen_units):
            if (max == 0):
                continue
            self.missed_events[i].SetPoint(self.missed_events[i].GetN(), ROOT.TDatime().Convert(), 1 - (self.num_hits[i] / max))
        self.num_events[0].GetYaxis().SetRangeUser(0, max * 1.2)

    def event_loop(self):
        with file_parser(self.file_path) as parser:
            for hits in parser:
                global running
                if (running == False):
                    print(f"Exiting is {running}")
                    break
                self.server.ProcessRequests()
                if hits is None:
                    print('sleeping')
                    self.update()
                    self.make_event_display()
                    time.sleep(2)
                    continue
                # print('reading')
                self.num_hits[hits[0].board] += 1
                for hit in hits:
                    if hit.trigger_id not in self.events:
                        self.events[hit.trigger_id] = event(hit.trigger_id)
                    self.events[hit.trigger_id].add_hit(hit)

                    self.last_hits[hit.board][hit.channel] = hit
                    self.low_gain_histograms[hit.board][hit.channel].Fill(hit.low_gain)
                    self.high_gain_histograms[hit.board][hit.channel].Fill(hit.high_gain)
                    self.combined_gain_histograms[hit.board][hit.channel].Fill(hit.comb_gain)
                    self.gain_correlations[hit.board][hit.channel].Fill(hit.high_gain, hit.low_gain)
                    self.overview_high_gain.Fill(hit.board * 100 + hit.channel, hit.high_gain)
                    self.overview_low_gain.Fill(hit.board * 100 + hit.channel, hit.low_gain)
                    self.overview_combined_gain.Fill(hit.board * 100 + hit.channel, hit.comb_gain)

                t = ROOT.TDatime().Convert()
                # print(f'Filling board {hits[0].board} at time {t} with {hits[0].trigger_id}')
                # events.append(hits)


    def make_event_display(self):
        self.event_display.Reset()
        # for i in range(2):
        #     for j in range(4):
        #         self.event_display.Fill(0, i, j, 0)
        #         self.event_display.Fill(66, i, j, 40000)
        event_number = self.last_hits[0][0].trigger_id
        while event_number not in self.events or self.events[event_number].is_complete_event() == False or self.events[event_number].max_adc < 500:
            event_number -= 1
            if event_number < 0:
                return
        event = self.events[event_number]
        # print(type(event))
        for i in range(self.caen_units):
            for j in range(self.channels):
                # print(f'Filling {i} {j}')
                hit = event.hits[j + 64 * i]
                if ((hit.board in (0, 1, 2, 3, 4, 7) and hit.comb_gain > 70) or (hit.board in (5, 6) and hit.comb_gain > 200)):
                    self.event_display.Fill(hit.z + 1, hit.x, hit.y, hit.comb_gain)
        

    
def main(argv):
    # Register the signal handler
    signal.signal(signal.SIGINT, handle_stop_signal)
    # monitor = online_monitor('data/Run68_list.txt')
    run_number = argv[1]
    ROOT.gStyle.SetOptStat(0)
    monitor = online_monitor(f'/home/lfhcal/Downloads/Janus_5202_3.6.0_20240514_linux/bin/DataFiles/Run{run_number}_list.txt', run_number)
    # monitor = online_monitor(f'data/Run{run_number}_list.txt')
    monitor.event_loop()
    print("Closing file")
    monitor.close()
    print("File closed")
    pass

if __name__ == '__main__':
    main(sys.argv)
