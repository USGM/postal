tracking_response = u"""<req:TrackingResponse xsi:schemaLocation="http://www.dhl.com TrackingResponse.xsd" xmlns:req="http://www.dhl.com" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
   <Response>
      <ServiceHeader>
         <MessageTime>2011-08-16T10:42:35+01:00</MessageTime>
         <MessageReference>1100000000000000000000000011</MessageReference>
         <SiteID>TestSiteID</SiteID>
      </ServiceHeader>
   </Response>
   <AWBInfo>
      <AWBNumber>9422367220</AWBNumber>
      <Status>
         <ActionStatus>success</ActionStatus>
      </Status>
      <ShipmentInfo>
         <OriginServiceArea>
            <ServiceAreaCode>HKG</ServiceAreaCode>
            <Description>HONG KONG - HONG KONG</Description>
         </OriginServiceArea>
         <DestinationServiceArea>
            <ServiceAreaCode>LEH</ServiceAreaCode>
            <Description>LE HAVRE - FRANCE</Description>
         </DestinationServiceArea>
         <ShipperName>TONTEC INTERNATIIONAL LIMITED</ShipperName>
         <ShipperAccountNumber>630276297</ShipperAccountNumber>
         <ConsigneeName>SCHNEIDER TOSHIBA INVERTER EUROPE</ConsigneeName>
         <ShipmentDate>2010-07-17T11:11:00</ShipmentDate>
         <Pieces>1</Pieces>
         <Weight>20.01</Weight>
         <WeightUnit>K</WeightUnit>
         <GlobalProductCode>P</GlobalProductCode>
         <ShipmentDesc>EXPRESS WORLDWIDE (nondoc)PLASTIC P</ShipmentDesc>
         <DlvyNotificationFlag>N</DlvyNotificationFlag>
         <Shipper>
            <City>KOWLOON</City>
            <CountryCode>HK</CountryCode>
         </Shipper>
         <Consignee>
            <City>EURE</City>
            <PostalCode>27120</PostalCode>
            <CountryCode>FR</CountryCode>
         </Consignee>
         <ShipperReference>
            <ReferenceID>8100048270</ReferenceID>
         </ShipperReference>
         <ShipmentEvent>
            <Date>2010-07-17</Date>
            <Time>11:11:00</Time>
            <ServiceEvent>
               <EventCode>PU</EventCode>
               <Description>Shipment picked up</Description>
            </ServiceEvent>
            <Signatory/>
            <ServiceArea>
               <ServiceAreaCode>HKG</ServiceAreaCode>
               <Description>HONG KONG - HONG KONG</Description>
            </ServiceArea>
         </ShipmentEvent>
         <ShipmentEvent>
            <Date>2010-07-19</Date>
            <Time>02:12:00</Time>
            <ServiceEvent>
               <EventCode>UD</EventCode>
               <Description>Clearance delay</Description>
            </ServiceEvent>
            <Signatory/>
            <ServiceArea>
               <ServiceAreaCode>CDG</ServiceAreaCode>
               <Description>PARIS - FRANCE</Description>
            </ServiceArea>
         </ShipmentEvent>
         <ShipmentEvent>
            <Date>2010-07-20</Date>
            <Time>12:29:00</Time>
            <ServiceEvent>
               <EventCode>WC</EventCode>
               <Description>With delivery courier</Description>
            </ServiceEvent>
            <Signatory/>
            <ServiceArea>
               <ServiceAreaCode>LEH</ServiceAreaCode>
               <Description>LE HAVRE - FRANCE</Description>
            </ServiceArea>
         </ShipmentEvent>
         <ShipmentEvent>
            <Date>2010-07-20</Date>
            <Time>13:28:00</Time>
            <ServiceEvent>
               <EventCode>RD</EventCode>
               <Description>Recipient refused delivery</Description>
            </ServiceEvent>
            <Signatory/>
            <ServiceArea>
               <ServiceAreaCode>LEH</ServiceAreaCode>
               <Description>LE HAVRE - FRANCE</Description>
            </ServiceArea>
         </ShipmentEvent>
         <ShipmentEvent>
            <Date>2010-07-20</Date>
            <Time>18:11:00</Time>
            <ServiceEvent>
               <EventCode>PL</EventCode>
               <Description>Processed at Location LE HAVRE - FRANCE</Description>
            </ServiceEvent>
            <Signatory/>
            <ServiceArea>
               <ServiceAreaCode>LEH</ServiceAreaCode>
               <Description>LE HAVRE - FRANCE</Description>
            </ServiceArea>
         </ShipmentEvent>
         <ShipmentEvent>
            <Date>2010-07-20</Date>
            <Time>19:36:00</Time>
            <ServiceEvent>
               <EventCode>DF</EventCode>
               <Description>Departed from DHL facility in LE HAVRE
                        - FRANCE</Description>
            </ServiceEvent>
            <Signatory/>
            <ServiceArea>
               <ServiceAreaCode>LEH</ServiceAreaCode>
               <Description>LE HAVRE - FRANCE</Description>
            </ServiceArea>
         </ShipmentEvent>
         <ShipmentEvent>
            <Date>2010-07-20</Date>
            <Time>21:04:00</Time>
            <ServiceEvent>
               <EventCode>AF</EventCode>
               <Description>Arrived at DHL facility in PARIS - FRANCE</Description>
            </ServiceEvent>
            <Signatory/>
            <ServiceArea>
               <ServiceAreaCode>CDG</ServiceAreaCode>
               <Description>PARIS - FRANCE</Description>
            </ServiceArea>
         </ShipmentEvent>
         <ShipmentEvent>
            <Date>2010-07-21</Date>
            <Time>17:28:00</Time>
            <ServiceEvent>
               <EventCode>PL</EventCode>
               <Description>Processed at Location LE HAVRE - FRANCE</Description>
            </ServiceEvent>
            <Signatory/>
            <ServiceArea>
               <ServiceAreaCode>LEH</ServiceAreaCode>
               <Description>LE HAVRE - FRANCE</Description>
            </ServiceArea>
         </ShipmentEvent>
         <ShipmentEvent>
            <Date>2010-07-21</Date>
            <Time>19:34:00</Time>
            <ServiceEvent>
               <EventCode>DF</EventCode>
               <Description>Departed from DHL facility in LE HAVRE
                        - FRANCE</Description>
            </ServiceEvent>
            <Signatory/>
            <ServiceArea>
               <ServiceAreaCode>LEH</ServiceAreaCode>
               <Description>LE HAVRE - FRANCE</Description>
            </ServiceArea>
         </ShipmentEvent>
         <ShipmentEvent>
            <Date>2010-07-21</Date>
            <Time>21:06:00</Time>
            <ServiceEvent>
               <EventCode>AF</EventCode>
               <Description>Arrived at DHL facility in PARIS - FRANCE</Description>
            </ServiceEvent>
            <Signatory/>
            <ServiceArea>
               <ServiceAreaCode>CDG</ServiceAreaCode>
               <Description>PARIS - FRANCE</Description>
            </ServiceArea>
         </ShipmentEvent>
         <ShipmentEvent>
            <Date>2010-07-22</Date>
            <Time>07:16:00</Time>
            <ServiceEvent>
               <EventCode>AR</EventCode>
               <Description>Arrived at DHL facility in PARIS - FRANCE</Description>
            </ServiceEvent>
            <Signatory/>
            <ServiceArea>
               <ServiceAreaCode>CDG</ServiceAreaCode>
               <Description>PARIS - FRANCE</Description>
            </ServiceArea>
         </ShipmentEvent>
         <ShipmentEvent>
            <Date>2010-07-22</Date>
            <Time>09:00:00</Time>
            <ServiceEvent>
               <EventCode>WC</EventCode>
               <Description>With delivery courier</Description>
            </ServiceEvent>
            <Signatory/>
            <ServiceArea>
               <ServiceAreaCode>CDG</ServiceAreaCode>
               <Description>PARIS - FRANCE</Description>
            </ServiceArea>
         </ShipmentEvent>
         <ShipmentEvent>
            <Date>2010-07-22</Date>
            <Time>12:25:00</Time>
            <ServiceEvent>
               <EventCode>OK</EventCode>
               <Description>Shipment delivered</Description>
            </ServiceEvent>
            <Signatory>GTW3700</Signatory>
            <ServiceArea>
               <ServiceAreaCode>CDG</ServiceAreaCode>
               <Description>PARIS - FRANCE</Description>
            </ServiceArea>
         </ShipmentEvent>
      </ShipmentInfo>
   </AWBInfo>
</req:TrackingResponse>"""


tracking_response_not_found = u"""<?xml version="1.0" encoding="UTF-8"?>
<req:TrackingResponse xmlns:req="http://www.dhl.com" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.dhl.com TrackingResponse.xsd">
    <Response>
        <ServiceHeader>
            <MessageTime>2017-05-03T13:12:39+01:00</MessageTime>
            <MessageReference>9131014351352841244932374744</MessageReference>
            <SiteID>1337766</SiteID>
        </ServiceHeader>
    </Response>
    <AWBInfo>
        <AWBNumber>1670466965</AWBNumber>
        <Status>
            <ActionStatus>No Shipments Found</ActionStatus>
            <Condition>
                <ConditionCode>209</ConditionCode>
                <ConditionData>No Shipments Found for AWBNumber 1670466965</ConditionData>
            </Condition>
        </Status>
    </AWBInfo>
    <LanguageCode>en</LanguageCode>
</req:TrackingResponse>"""
