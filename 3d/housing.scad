part = "assembly";
swing = 0; // 0 closed, 180 folded open
pin_lift = 0; // 0 seated, 3 retracted

enclosed_dia = 160; // valid 120-220
arc_w = 20;
arc_t = 13;
wall = 2.5;
clr = 0.25;

jgy_gear = [46, 32, 25];
jgy_motor_d = 24.4;
jgy_motor_l = 30.8;
jgy_shaft_d = 6;
jgy_shaft_l = 14;
jgy_shaft_flat = 2.55;
jgy_shaft_from_end = 9;
jgy_mount_dx = 33; jgy_mount_dy = 18;

pcb = [55, 40, 1.6];
pcb_inset = 3.5;
pcb_standoff = 5;
bat = [34, 50, 11];
d2f = [12.8, 5.8, 6.5];
d2f_hole_pitch = 6.5;
servo_cav = [24, 13.5, 26];
pin_d = 5;
collar_d = 9;
camlock_d = 12;
spring_d = 9.5;
btn_d = 6.5;

Ri = enclosed_dia/2;
Rc = Ri + arc_w/2;
Ro = Ri + arc_w;
hx = -Rc;
house_or = Ro + 26;
floor_t = wall;
H = floor_t + jgy_gear[2] + wall;
seam = H - 8;
za0 = H;
za1 = H + arc_t;
zs0 = za1;
zs1 = za1 + arc_t;
zpin = zs0 + arc_t/2;
rec_x0 = Ri; rec_x1 = Ro + 16;
rec_y0 = -20; rec_y1 = 22;
rec_top = zs1 + 3;
fixed_a0 = 190;
boss_d = 24;
lobe_x0 = -(Rc + jgy_gear[0] - jgy_shaft_from_end + jgy_motor_l + 4);
lobe_hw = jgy_gear[1]/2 + clr + wall + 1;

boss_pts = [for (a=[205,245,288,320,348]) (Ri+33)*[cos(a),sin(a)]];
lobe_boss = [[-Rc-45, 15.5], [-Rc-45, -15.5]];
screw_pts = concat(boss_pts, lobe_boss);

$fa = 3; $fs = 0.5;

module ring(r0, r1, h, a0, a1, round_r=0)
  rotate([0,0,a0]) rotate_extrude(angle=a1-a0)
    translate([r0,0]) offset(round_r) offset(-round_r) square([r1-r0, h]);

module rbox(x0, x1, y0, y1, r=4)
  offset(r) offset(-r) translate([x0,y0]) square([x1-x0, y1-y0]);

module chamfered(h, cb=0, ct=0, n=5) { // stepped edge chamfer on 2D child
  translate([0,0,cb]) linear_extrude(h - cb - ct) children();
  for (i=[0:n-1]) {
    if (cb > 0) translate([0,0,cb*i/n]) linear_extrude(cb/n + 0.02)
      offset(-cb*(n-i)/n) children();
    if (ct > 0) translate([0,0,h - ct*(n-i)/n - 0.02]) linear_extrude(ct/n + 0.02)
      offset(-ct*(i+1)/n) children();
  }
}

module plan2d() offset(2) offset(-2) union() {
  difference() {
    circle(house_or);
    circle(Ri);
    translate([-2*house_or, 1]) square([4*house_or, 2*house_or]);
  }
  rbox(lobe_x0, -Ri, -lobe_hw, lobe_hw);
  rbox(rec_x0, rec_x1, rec_y0, rec_y1);
  rbox(-pcb[0]/2 - 6, pcb[0]/2 + 6, pcb_wall_y, -Ri - 15); // flat wall bump clears PCB corners
}

module cavity2d() offset(-wall) plan2d();

module motor_void() {
  gx1 = -(Rc - jgy_shaft_from_end);
  translate([gx1 - jgy_gear[0] - clr, -jgy_gear[1]/2 - clr, floor_t])
    cube([jgy_gear[0] + 2*clr, jgy_gear[1] + 2*clr, jgy_gear[2] + clr]);
  translate([gx1 - jgy_gear[0], 0, floor_t + jgy_gear[2]/2])
    rotate([0,-90,0]) cylinder(d=jgy_motor_d + 2*clr, h=jgy_motor_l + 2);
}

module d2f_pocket(depth)
  translate([0,0,-depth]) {
    translate([-d2f[0]/2 - clr, -d2f[1]/2 - clr]) cube([d2f[0]+2*clr, d2f[1]+2*clr, depth+2*arc_t]);
    for (s=[-1,1]) translate([s*d2f_hole_pitch/2, 0, -6]) cylinder(d=1.9, h=6.1);
  }

module wall_slot(ang, zc, w, h, d=wall+2) // radial slot through outer wall
  rotate([0,0,ang]) translate([house_or + 1 - d, 0, zc]) rotate([0,90,0])
    hull() for (s=[-1,1]) translate([0, s*(w-h)/2]) cylinder(d=h, h=d);

pcb_c = [0, -(Ri + wall + pcb[1]/2 + 1)];
pcb_wall_y = pcb_c[1] - pcb[1]/2 - 0.3 - wall;
pcb_holes = [for (sx=[-1,1], sy=[-1,1])
  pcb_c + [sx*(pcb[0]/2 - pcb_inset), sy*(pcb[1]/2 - pcb_inset)]];
usb_z = floor_t + pcb_standoff + pcb[2] + 1.7;
btn_a = 283; btn_z = usb_z + 1; // radial axis at PCB button corner
btn_or = -pcb_wall_y/abs(sin(btn_a)); // outer face along button axis through flat bump

module button_cap() {
  cylinder(d=3, h=2);
  translate([0,0,2]) cylinder(d=9, h=1.2);
  translate([0,0,3.2]) cylinder(d=btn_d, h=1.8);
  intersection() {
    translate([0,0,1.2]) sphere(r=5);
    translate([0,0,5]) cylinder(d=btn_d, h=1.3);
  }
}

module btn_place()
  rotate([0,0,btn_a]) translate([btn_or - wall - 3.2, 0, btn_z]) rotate([0,90,0]) children();

module button_bore() rotate([0,0,btn_a]) translate([0,0,btn_z]) rotate([0,90,0]) {
  translate([0,0,btn_or - wall - 1]) cylinder(d=btn_d + 0.3, h=wall + 3);
  translate([0,0,btn_or - 1.6]) cylinder(d1=btn_d + 0.3, d2=btn_d + 5.5, h=2.6); // covers oblique face
}

module housing_inner() difference() {
  union() {
    difference() {
      chamfered(seam, cb=1) plan2d();
      translate([0,0,floor_t]) linear_extrude(seam) cavity2d();
    }
    for (p=pcb_holes) translate([p[0], p[1], 0]) cylinder(d=5.5, h=floor_t+pcb_standoff);
    rotate([0,0,232]) translate([Ri+23, 0, 0]) rotate([0,0,-90])
      linear_extrude(floor_t + 8) difference() {
        rbox(-bat[0]/2-clr-2, bat[0]/2+clr+2, -bat[1]/2-clr-2, bat[1]/2+clr+2, 2);
        rbox(-bat[0]/2-clr, bat[0]/2+clr, -bat[1]/2-clr-3, bat[1]/2+clr, 1);
      }
    for (p=screw_pts) translate([p[0], p[1], 0]) cylinder(d=6.5, h=seam);
  }
  motor_void();
  translate([0,0,seam-1.6]) linear_extrude(3) difference()
    { offset(-0.6) plan2d(); offset(-1.9) plan2d(); }
  for (p=pcb_holes) translate([p[0], p[1], floor_t]) cylinder(d=2.1, h=pcb_standoff+6);
  for (p=screw_pts) translate([p[0], p[1], 4]) cylinder(d=2.5, h=seam);
  wall_slot(270, usb_z, 9.4, 3.8);
  wall_slot(270, usb_z, 13, 7.2, 2.2); // plug body recess
  button_bore();
}

pin_y = 6;
slot_x0 = Ro - 0.5; slot_x1 = Ro + 7.5; // collar travel slot
cam_x = Ro + 3.5;
endstop_a = [250, 70]; // closed, open azimuth about hinge

module fixed_arc_solid() {
  translate([0,0,za0]) ring(Ri, Ro, arc_t, fixed_a0, 360, 2);
  translate([0,0,za0]) chamfered(rec_top - za0, ct=1) rbox(rec_x0, rec_x1, rec_y0, rec_y1);
}

module seat_pocket() {
  translate([Ri-0.4, -0.5, zs0-0.4]) cube([arc_w+0.8, rec_y1+1, arc_t+0.8]);
  translate([Ri-0.4, 10, zs0-0.4]) cube([arc_w+0.8, rec_y1, rec_top]); // open top past roof
  translate([Ri-6, rec_y1-4, zs0+2]) rotate([45,0,0]) cube([arc_w+12, 10, 10]); // roof entry chamfer
}

module latch_bores() {
  translate([Ri+4, pin_y, zpin]) rotate([0,90,0]) cylinder(d=pin_d+0.4, h=rec_x1-Ri-4.5);
  translate([Rc+16, pin_y, zpin]) rotate([0,90,0]) cylinder(d=spring_d+0.3, h=rec_x1-Rc-17);
  translate([slot_x0, pin_y-collar_d/2-0.3, 24]) // collar + servo horn slot
    cube([slot_x1-slot_x0, collar_d+0.6, zpin+collar_d/2+0.3-24]);
  translate([cam_x, pin_y, zpin+2]) cylinder(d=camlock_d+0.3, h=rec_top); // cam lock barrel
  translate([cam_x, pin_y, rec_top-1.3]) cylinder(d1=camlock_d+0.3, d2=camlock_d+3.3, h=1.4); // flush face ring
  translate([Ri+8, pin_y, za0+3]) cube([13.3, 6.3, 6.9], center=true); // latch-sense switch
  translate([Ri+8, (rec_y0+pin_y)/2, za0+3]) cube([6.3, pin_y-rec_y0, 6.9], center=true);
  translate([Ri+8, pin_y, za0+5]) cylinder(d=2, h=zs0-za0-4.5); // plunger to seat floor
  translate([Ri+8, pin_y, 20]) cylinder(d=3, h=za0-19); // switch wire drop
}

module servo_void()
  translate([Rc+8 - servo_cav[0]/2, pin_y - servo_cav[1]/2, seam-1])
    cube(servo_cav);

gearbox_cx = -(Rc - jgy_shaft_from_end) - jgy_gear[0]/2;

module housing_lid(arc=true) difference() {
  union() {
    difference() {
      chamfered(H - seam, ct=1) plan2d();
      translate([0,0,-1]) linear_extrude(H - seam - wall + 1) cavity2d();
    }
    translate([0,0,-1.4]) linear_extrude(1.4) difference()
      { offset(-0.75) plan2d(); offset(-1.75) plan2d(); }
    if (arc) translate([0,0,-seam]) fixed_arc_solid();
    translate([hx, 0, H - seam]) cylinder(d=11, h=3);
  }
  translate([hx, 0, -2]) cylinder(d=jgy_shaft_d + 0.6, h=H - seam + 5.5);
  for (sx=[-1,1], sy=[-1,1])
    translate([gearbox_cx + sx*jgy_mount_dx/2, sy*jgy_mount_dy/2, -1])
      cylinder(d=3.2, h=H - seam + 2);
  for (p=screw_pts) translate([p[0], p[1], -2]) {
    cylinder(d=3.2, h=H - seam + 4);
    translate([0,0,2 + H - seam - 2.5]) cylinder(d=6.2, h=40);
  }
  for (i=[0,1]) let(a=endstop_a[i])
    translate([hx + 17*cos(a), 17*sin(a), H - seam]) rotate([0,0,a+90]) d2f_pocket(2);
  translate([0,0,-seam]) {
    seat_pocket();
    latch_bores();
    servo_void();
    motor_void();
  }
}

module arc_swing_solid() {
  translate([0,0,zs0]) ring(Ri, Ro, arc_t, 0, 180, 2);
  translate([hx, 0, H+3.5]) cylinder(d=boss_d, h=zs1 - H - 3.5);
  translate([hx, 0, H+3.5]) rotate([0,0,endstop_a[0]])
    translate([boss_d/2 - 2, -2.5, 0]) cube([18 - boss_d/2 + 2, 5, 3]);
}

module arc_swing() difference() {
  arc_swing_solid();
  translate([hx, 0, H+3.4]) linear_extrude(42 - H - 3.4) difference() {
    circle(d=jgy_shaft_d + 0.15);
    translate([jgy_shaft_flat, -5]) square(10);
  }
  translate([hx, 0, 38]) rotate([0,-90,0]) cylinder(d=2.6, h=boss_d/2 + 2);
  translate([0,0,zpin]) rotate([0,0,-2]) rotate_extrude(angle=170)
    translate([Rc,0]) circle(d=6.2);
  translate([Ro+2, 2, zs0-1]) rotate([0,0,45]) cube([14,14,arc_t+2], center=true);
  translate([Rc+3, pin_y, zpin]) rotate([0,90,0]) cylinder(d=pin_d+0.4, h=arc_w/2+3);
}

module latch_pin_part() translate([Rc+1.5, pin_y, zpin]) rotate([0,90,0]) {
  cylinder(d1=3, d2=pin_d, h=1.5);
  translate([0,0,1.5]) cylinder(d=pin_d, h=18.5);
  translate([0,0,10]) cylinder(d=collar_d, h=3);
}

module arc_fixed() difference() {
  fixed_arc_solid();
  seat_pocket();
  latch_bores();
}

module assembly() {
  color("dimgray") housing_inner();
  color("slategray") translate([0,0,seam]) housing_lid(arc=false);
  color("steelblue") arc_fixed();
  color("orange") translate([hx,0,0]) rotate([0,0,swing]) translate([-hx,0,0]) arc_swing();
  color("crimson") translate([pin_lift,0,0]) latch_pin_part();
  color("gold") btn_place() button_cap();
}

if (part == "housing_inner") housing_inner();
else if (part == "housing_lid") housing_lid();
else if (part == "arc_fixed") translate([0,0,-za0]) arc_fixed();
else if (part == "arc_swing") translate([0,0,-(H+3.5)]) arc_swing();
else if (part == "latch_pin") translate([-Rc-1.5, -pin_y, -zpin+pin_d/2]) latch_pin_part();
else if (part == "button_cap") button_cap();
else assembly();
